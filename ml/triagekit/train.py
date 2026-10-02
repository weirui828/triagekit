"""One training run: fit on train, select policy on validation, evaluate test once policies are frozen."""
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from importlib.metadata import version as pkg_version
from pathlib import Path

import mlflow
import numpy as np

from .device import resolve_device
from .evaluate import METRICS_VERSION, classification_metrics, routing_metrics
from .models import get_model
from .policy import select_policy
from .pyfunc_model import ARTIFACT_KEY, TriagePyfunc, write_package
from .schemas import Row, RunManifest, TrainConfig
from .settings import mlflow_artifact_root, mlflow_uri
from .snapshot import load_snapshot

TAG = "triagekit"


def setup_mlflow(experiment: str) -> None:
    mlflow.set_tracking_uri(mlflow_uri())
    if mlflow.get_experiment_by_name(experiment) is None:
        mlflow.create_experiment(experiment, artifact_location=str(Path(mlflow_artifact_root()) / experiment))
    mlflow.set_experiment(experiment)


def _xy(rows: list[Row], split: str):
    rs = [r for r in rows if r.split == split and r.label is not None]
    return rs, [r.text for r in rs], np.array([r.label for r in rs], dtype=int), [r.category for r in rs]


def _dependency_versions() -> dict[str, str]:
    out = {}
    for p in ("scikit-learn", "numpy", "mlflow", "pydantic", "torch", "transformers"):
        try:
            out[p] = pkg_version(p)
        except Exception:
            pass
    import platform
    out["python"] = platform.python_version()
    return out


def _code_revision() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None


def run_training(cfg: TrainConfig, job_id: str | None = None, log=print) -> str:
    t0 = time.time()
    manifest, contract, rows = load_snapshot(cfg.snapshot_id)
    _, x_tr, y_tr, _ = _xy(rows, "train")
    val_rows, x_va, y_va, c_va = _xy(rows, "validation")
    test_rows, x_te, y_te, c_te = _xy(rows, "test")
    if len(x_tr) == 0 or len(x_va) == 0:
        raise ValueError(f"snapshot needs labeled train and validation rows (train={len(x_tr)}, validation={len(x_va)})")
    if len(set(y_tr.tolist())) < 2:
        raise ValueError("training data must contain both classes")
    device = resolve_device(cfg.device)
    log(f"snapshot={cfg.snapshot_id} train={len(x_tr)} validation={len(x_va)} test={len(x_te)} device={device}")

    setup_mlflow(cfg.experiment)
    with mlflow.start_run(run_name=f"{cfg.model}-{cfg.snapshot_id[:8]}") as run:
        rid = run.info.run_id
        log(f"mlflow run_id={rid}")
        model = get_model(cfg.model, cfg.params.model_dump(), manifest.preprocessing, cfg.seed, device)
        model.log = log
        model.fit(x_tr, y_tr, x_va, y_va)
        p_va = model.predict_proba(x_va)
        policy, sweep = select_policy(y_va, p_va, contract)  # validation only
        log(f"threshold={policy.classification_threshold} routing=[{policy.routing_low}, {policy.routing_high}] "
            f"feasible={policy.routing_feasible} notes={policy.notes}")
        val_m = classification_metrics(y_va, p_va, policy.classification_threshold, c_va)
        val_r = routing_metrics(y_va, p_va, policy.classification_threshold, policy.routing_low, policy.routing_high)
        test_m = test_r = None
        preds = []
        if len(x_te):
            p_te = model.predict_proba(x_te)
            test_m = classification_metrics(y_te, p_te, policy.classification_threshold, c_te)
            test_r = routing_metrics(y_te, p_te, policy.classification_threshold, policy.routing_low, policy.routing_high)
            preds = [{"id": r.id, "label": int(y), "probability": float(p), "predicted_label": int(p >= policy.classification_threshold),
                      "category": r.category} for r, y, p in zip(test_rows, y_te, p_te)]
        duration = time.time() - t0
        run_manifest = RunManifest(
            run_id=rid, job_id=job_id, dataset_id=manifest.dataset_id, snapshot_id=manifest.snapshot_id,
            snapshot_hash=manifest.snapshot_hash, training_data_hash=manifest.training_data_hash,
            split_manifest_hash=manifest.split_manifest_hash, evaluation_hash=manifest.evaluation_hash,
            contract_version=manifest.contract_version, contract_hash=manifest.contract_hash, model=cfg.model,
            checkpoint=getattr(model, "checkpoint", None), preprocessing=manifest.preprocessing, params=cfg.params.model_dump(),
            seed=cfg.seed, device=device, code_revision=_code_revision(),
            dependency_versions=_dependency_versions(),
            duration_seconds=round(duration, 3), metric_definitions_version=METRICS_VERSION)

        mlflow.log_params({"model": cfg.model, "seed": cfg.seed, "device": device, "snapshot_id": cfg.snapshot_id,
                           **{f"param_{k}": v for k, v in cfg.params.model_dump().items()}})
        mlflow.set_tags({f"{TAG}.{k}": v for k, v in {
            "job_id": job_id or "", "snapshot_id": manifest.snapshot_id, "snapshot_hash": manifest.snapshot_hash,
            "evaluation_hash": manifest.evaluation_hash, "split_manifest_hash": manifest.split_manifest_hash,
            "contract_version": manifest.contract_version, "contract_hash": manifest.contract_hash,
            "metrics_version": METRICS_VERSION, "routing_feasible": str(policy.routing_feasible).lower(),
            "threshold_feasible": str(policy.threshold_feasible).lower(), "model": cfg.model}.items()})
        metrics = {"val_macro_f1": val_m.macro_f1, "val_positive_precision": val_m.positive_precision,
                   "val_positive_recall": val_m.positive_recall, "val_coverage": val_r.coverage,
                   "val_auto_error_rate": val_r.auto_error_rate, "threshold": policy.classification_threshold,
                   "routing_low": policy.routing_low, "routing_high": policy.routing_high, "duration_seconds": duration}
        if test_m:
            metrics |= {"test_macro_f1": test_m.macro_f1, "test_positive_precision": test_m.positive_precision,
                        "test_positive_recall": test_m.positive_recall, "test_coverage": test_r.coverage,
                        "test_auto_error_rate": test_r.auto_error_rate}
        mlflow.log_metrics({k: v for k, v in metrics.items() if v is not None})

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            dump = lambda name, obj: (d / name).write_text(json.dumps(obj, indent=2))
            dump("manifest.json", run_manifest.model_dump(mode="json"))
            dump("policy.json", policy.model_dump(mode="json"))
            dump("threshold_sweep.json", [p.model_dump(mode="json") for p in sweep])
            dump("training_history.json", {"history": getattr(model, "history", []), "best_epoch": getattr(model, "best_epoch", None)})
            dump("metrics_validation.json", {"classification": val_m.model_dump(mode="json"), "routing": val_r.model_dump(mode="json")})
            dump("metrics_test.json", {"classification": test_m.model_dump(mode="json") if test_m else None,
                                       "routing": test_r.model_dump(mode="json") if test_r else None})
            (d / "predictions_test.jsonl").write_text("".join(json.dumps(p) + "\n" for p in preds))
            for f in d.iterdir():
                mlflow.log_artifact(str(f))
            pkg = write_package(d / "pkg", model, policy, contract, {
                "run_id": rid, "snapshot_id": manifest.snapshot_id, "contract_hash": manifest.contract_hash,
                "preprocessing": manifest.preprocessing.model_dump(mode="json"), "class_mapping": {"0": contract.negative.name, "1": contract.positive.name}})
            info = mlflow.pyfunc.log_model(name="model", python_model=TriagePyfunc(), artifacts={ARTIFACT_KEY: str(pkg)},
                                           pip_requirements=[f"scikit-learn=={pkg_version('scikit-learn')}", f"mlflow=={pkg_version('mlflow')}"])
            mlflow.set_tags({f"{TAG}.model_uri": info.model_uri, f"{TAG}.model_id": info.model_id or ""})
        log(f"done in {duration:.1f}s val_macro_f1={val_m.macro_f1} test_macro_f1={test_m.macro_f1 if test_m else None}")
        return rid
