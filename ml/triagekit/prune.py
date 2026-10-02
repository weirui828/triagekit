"""Explicit, dry-run-first pruning of unpromoted run weights. Metrics, manifests and predictions are kept."""
import shutil
from pathlib import Path

from . import jobs, registry
from .runs import client
from .schemas import PruneCandidate, PruneResponse
from .train import TAG


def _dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


def _weights_dir(c, model_id: str | None) -> Path | None:
    if not model_id:
        return None
    try:
        loc = c.get_logged_model(model_id).artifact_location
    except Exception:
        return None
    if loc.startswith("file://"):
        loc = loc[len("file://"):]
    p = Path(loc) / "artifacts" / "package" / "weights"
    return p if p.exists() else None


def prune(dry_run: bool = True, experiment: str | None = None) -> PruneResponse:
    c = client()
    exps = [c.get_experiment_by_name(experiment)] if experiment else c.search_experiments()
    exp_ids = [e.experiment_id for e in exps if e is not None]
    protected_runs = set()
    for v in registry.protected_versions():
        try:
            protected_runs.add(c.get_model_version(registry.REGISTERED_MODEL_NAME, v).run_id)
        except Exception:
            pass
    active = {j.run_id for j in jobs.list_jobs().jobs if j.status in jobs.ACTIVE and j.run_id} | {
        j.job_id for j in jobs.list_jobs().jobs if j.status in jobs.ACTIVE}
    pruned, protected, freed = [], [], 0
    for run in c.search_runs(exp_ids, max_results=5000):
        rid = run.info.run_id
        tags = run.data.tags
        model_id = tags.get(f"{TAG}.model_id") or None
        wdir = _weights_dir(c, model_id)
        size = _dir_size(wdir) if wdir else 0
        if tags.get(f"{TAG}.pruned") == "true" or wdir is None:
            continue
        if rid in protected_runs:
            protected.append(PruneCandidate(run_id=rid, model_id=model_id, bytes=size, reason="promoted (current or rollback target)"))
            continue
        if rid in active or tags.get(f"{TAG}.job_id") in active or run.info.status == "RUNNING":
            protected.append(PruneCandidate(run_id=rid, model_id=model_id, bytes=size, reason="active job"))
            continue
        pruned.append(PruneCandidate(run_id=rid, model_id=model_id, bytes=size, reason="unpromoted, unreferenced"))
        freed += size
        if not dry_run:
            shutil.rmtree(wdir)
            c.set_tag(rid, f"{TAG}.pruned", "true")
    return PruneResponse(dry_run=dry_run, pruned=pruned, protected=protected, bytes_freed=freed)
