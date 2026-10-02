"""Replicates the human-loop TWCS DistilBERT run against replication/twcs_distilbert.json."""
import json
import platform
from datetime import datetime, timezone
from importlib.metadata import version as pkg_version
from pathlib import Path

from .adapters.twcs import file_sha256, load_labeled_twcs, original_protocol_splits, split_hashes
from .contract import load_contract_file, validate_contract
from .device import resolve_device
from .schemas import DistilbertParams, PreprocessingConfig, SnapshotExportRequest, TrainConfig
from .settings import data_dir
from .snapshot import export_snapshot

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "replication" / "twcs_distilbert.json"
CONTRACT = ROOT / "examples" / "twcs.contract.yaml"
NO_PREPROCESSING = PreprocessingConfig(lowercase=False, collapse_whitespace=False, strip_urls=False, max_chars=1_000_000)


class Prerequisite(Exception):
    pass


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def prepare_snapshot(data_csv: str | Path, manifest: dict) -> tuple[str, dict]:
    """Verifies the data file and split against the manifest, then exports (or reuses) the replication snapshot."""
    data_csv = Path(data_csv)
    if not data_csv.exists():
        raise Prerequisite(f"labeled TWCS file not found: {data_csv} (expected {manifest['dataset']['file']} from the human-loop repo)")
    sha = file_sha256(data_csv)
    if sha != manifest["dataset"]["sha256"]:
        raise Prerequisite(f"data hash mismatch: {sha} != manifest {manifest['dataset']['sha256']}; this is not the original file")
    rows = load_labeled_twcs(data_csv)
    assign = original_protocol_splits(rows)
    hashes = split_hashes(assign)
    for k, v in hashes.items():
        if manifest["split"][k] != v:
            raise Prerequisite(f"split {k} differs from manifest: {v} != {manifest['split'][k]}")
    rows = [r.model_copy(update={"split": assign[r.id]}) for r in rows]
    contract = validate_contract(load_contract_file(CONTRACT)).contract
    snapshot_id = f"twcs-replication-{sha[:12]}"
    res = export_snapshot(SnapshotExportRequest(snapshot_id=snapshot_id, dataset_id="twcs-llm-labeled-5k", contract=contract,
                                                preprocessing=NO_PREPROCESSING, rows=rows))
    return snapshot_id, {"data_sha256": sha, **hashes, "snapshot_hash": res.manifest.snapshot_hash, "snapshot_created": res.created}


def run_replication(data_csv: str | Path, seeds: list[int], device: str = "auto", log=print) -> dict:
    from .runs import summarize
    from .train import run_training
    manifest = load_manifest()
    snapshot_id, prep = prepare_snapshot(data_csv, manifest)
    log(f"snapshot {snapshot_id} ready (created={prep['snapshot_created']})")
    dev = resolve_device(device)
    tol = manifest["tolerance"]
    reported = manifest["reported"]["per_seed_test_macro_f1"]
    hp = manifest["hyperparameters"]
    params = DistilbertParams(checkpoint=manifest["model"]["checkpoint"], epochs=hp["epochs"], batch_size=hp["batch_size"],
                              learning_rate=hp["learning_rate"], max_length=hp["max_length"], warmup_ratio=hp["warmup_ratio"],
                              weight_decay=hp["weight_decay"], grad_clip_norm=hp["grad_clip_norm"], class_weighted_loss=hp["class_weighted_loss"])
    results = []
    for seed in seeds:
        log(f"--- seed {seed} on {dev}")
        rid = run_training(TrainConfig(snapshot_id=snapshot_id, model="distilbert", params=params, seed=seed, device=dev,
                                       experiment="twcs-replication"), log=log)
        s = summarize(rid)
        f1 = s.test.macro_f1 if s.test else None
        exp = reported.get(str(seed))
        results.append({"seed": seed, "run_id": rid, "test_macro_f1": f1, "reported": exp,
                        "delta": None if f1 is None or exp is None else round(f1 - exp, 4),
                        "within_tolerance": None if f1 is None or exp is None else abs(f1 - exp) <= tol["per_seed_abs"],
                        "validation_macro_f1": s.validation.macro_f1 if s.validation else None,
                        "confusion": s.test.confusion.model_dump() if s.test else None,
                        "policy": s.policy.model_dump() if s.policy else None})
        log(f"seed {seed}: test macro F1 {f1} vs reported {exp}")
    f1s = [r["test_macro_f1"] for r in results if r["test_macro_f1"] is not None]
    mean = round(sum(f1s) / len(f1s), 4) if f1s else None
    all_three = sorted(seeds) == sorted(int(k) for k in reported)
    mean_ok = None
    if all_three and mean is not None:
        mean_ok = abs(mean - manifest["reported"]["mean_macro_f1"]) <= tol["three_seed_mean_abs"]
    env = {"python": platform.python_version(), "device": dev, "platform": platform.platform()}
    for p in ("torch", "transformers", "scikit-learn", "mlflow"):
        try:
            env[p] = pkg_version(p)
        except Exception:
            env[p] = None
    env_diffs = {k: (env.get(k), manifest["environment"].get(k)) for k in ("python", "torch", "transformers", "scikit-learn")
                 if env.get(k) != manifest["environment"].get(k)}
    report = {
        "manifest": manifest["name"], "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "snapshot_id": snapshot_id,
        "prerequisites": prep, "environment": env, "environment_differences_from_original": env_diffs,
        "same_protocol": True, "per_seed": results, "mean_test_macro_f1": mean,
        "reported_mean": manifest["reported"]["mean_macro_f1"], "three_seed_mean_within_tolerance": mean_ok,
        "all_seeds_within_tolerance": all(r["within_tolerance"] for r in results if r["within_tolerance"] is not None),
        "tolerance": tol,
        "note": "Scores measure agreement with LLM-generated labels on the original row-level split. "
                "Environment differences are listed above; a pass under a different environment is a replication of the protocol, not a bit-exact reproduction.",
    }
    out = data_dir() / "replication"
    out.mkdir(exist_ok=True)
    path = out / f"twcs_distilbert_{report['at'].replace(':', '')}.json"
    path.write_text(json.dumps(report, indent=2))
    report["report_path"] = str(path)
    return report
