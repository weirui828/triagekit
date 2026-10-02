"""Builds the tracked demo model from the example data. No MLflow tracking; provenance is written alongside."""
import json
import shutil
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version as pkg_version
from pathlib import Path

import mlflow.pyfunc
import numpy as np

from .contract import load_contract_file, validate_contract
from .evaluate import classification_metrics, routing_metrics
from .hashing import sha256_text
from .models import get_model
from .policy import select_policy
from .pyfunc_model import ARTIFACT_KEY, TriagePyfunc, write_package
from .schemas import PreprocessingConfig, SnapshotExportRequest
from .snapshot import compute_hashes, export_snapshot
from .splits import assign_splits
from .validate import parse_csv_file, validate_rows

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def build_bundled_model(out: Path, seed: int = 42) -> dict:
    csv_path, contract_path = EXAMPLES / "support_demo.csv", EXAMPLES / "support_demo.contract.yaml"
    contract = validate_contract(load_contract_file(contract_path)).contract
    res = validate_rows(contract, parse_csv_file(csv_path))
    if not res.report.ok:
        raise ValueError(res.report.errors)
    by_id = {a.id: a.split for a in assign_splits(res.rows, seed=seed).assignments}
    rows = [r.model_copy(update={"split": by_id[r.id]}) for r in res.rows]
    pre = PreprocessingConfig()
    with tempfile.TemporaryDirectory() as td:
        snap = export_snapshot(SnapshotExportRequest(snapshot_id="bundled", dataset_id="support_demo", contract=contract,
                                                     preprocessing=pre, rows=rows), root=Path(td)).manifest
        tr = [r for r in rows if r.split == "train" and r.label is not None]
        va = [r for r in rows if r.split == "validation" and r.label is not None]
        te = [r for r in rows if r.split == "test" and r.label is not None]
        model = get_model("tfidf_lr", {}, pre, seed, "cpu")
        model.fit([r.text for r in tr], np.array([r.label for r in tr]))
        y_va, p_va = np.array([r.label for r in va]), model.predict_proba([r.text for r in va])
        policy, _ = select_policy(y_va, p_va, contract)
        y_te, p_te = np.array([r.label for r in te]), model.predict_proba([r.text for r in te])
        t = policy.classification_threshold
        metrics = {"validation": classification_metrics(y_va, p_va, t).model_dump(),
                   "test": classification_metrics(y_te, p_te, t).model_dump(),
                   "test_routing": routing_metrics(y_te, p_te, t, policy.routing_low, policy.routing_high).model_dump()}
        pkg = write_package(Path(td) / "pkg", model, policy, contract, {
            "run_id": None, "snapshot_id": "bundled", "contract_hash": snap.contract_hash, "preprocessing": pre.model_dump(),
            "class_mapping": {"0": contract.negative.name, "1": contract.positive.name}})
        if out.exists():
            shutil.rmtree(out)
        mlflow.pyfunc.save_model(path=str(out), python_model=TriagePyfunc(), artifacts={ARTIFACT_KEY: str(pkg)},
                                 pip_requirements=[f"scikit-learn=={pkg_version('scikit-learn')}", f"mlflow=={pkg_version('mlflow')}"])
    for junk in ("uv.lock", "pyproject.toml", ".python-version"):
        (out / junk).unlink(missing_ok=True)
    prov = {"note": "DEMO artifact trained on synthetic templated data; metrics are not evidence for real datasets",
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "dataset": str(csv_path.name),
            "dataset_sha256": sha256_text(csv_path.read_text()), "contract_version": contract.contract_version,
            "contract_hash": snap.contract_hash, "seed": seed, "split_counts": snap.split_counts,
            "policy": policy.model_dump(), "metrics": metrics,
            "dependency_versions": {p: pkg_version(p) for p in ("scikit-learn", "numpy", "mlflow")}}
    (out / "provenance.json").write_text(json.dumps(prov, indent=2))
    return prov
