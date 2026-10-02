"""Read MLflow runs into summaries and check comparison compatibility."""
import json
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient

from .evaluate import METRICS_VERSION
from .schemas import (ClassificationMetrics, CompareResponse, PolicySelection, PredictionRow, PredictionsResponse,
                      RoutingMetrics, RunDetail, RunListResponse, RunManifest, RunSummary, ThresholdSweepPoint)
from .settings import mlflow_uri
from .train import TAG

# evaluation_hash covers the evaluation examples' ids, splits, labels and text; the full split manifest may
# legitimately grow as reviewed production rows join the training split.
COMPARE_KEYS = ("evaluation_hash", "contract_hash", "contract_version", "metrics_version")


def client() -> MlflowClient:
    mlflow.set_tracking_uri(mlflow_uri())
    return MlflowClient()


def _artifact(c: MlflowClient, run_id: str, name: str):
    try:
        return json.loads(Path(c.download_artifacts(run_id, name)).read_text())
    except Exception:
        return None


def summarize(run_id: str, detail: bool = False) -> RunSummary | RunDetail:
    c = client()
    run = c.get_run(run_id)
    tags = run.data.tags
    manifest = _artifact(c, run_id, "manifest.json")
    policy = _artifact(c, run_id, "policy.json")
    val = _artifact(c, run_id, "metrics_validation.json") or {}
    test = _artifact(c, run_id, "metrics_test.json") or {}
    pruned = tags.get(f"{TAG}.pruned") == "true"
    reason = None
    if run.info.status != "FINISHED":
        reason = f"run status is {run.info.status}"
    elif not policy:
        reason = "run has no policy artifact"
    elif not policy["routing_feasible"] or not policy["threshold_feasible"]:
        reason = "policy constraints infeasible on validation: " + "; ".join(policy.get("notes", []))
    elif pruned:
        reason = "run weights were pruned; retrain to promote"
    kw = dict(
        run_id=run_id, status=run.info.status,
        start_time=str(run.info.start_time) if run.info.start_time else None,
        manifest=RunManifest(**manifest) if manifest else None,
        policy=PolicySelection(**policy) if policy else None,
        validation=ClassificationMetrics(**val["classification"]) if val.get("classification") else None,
        test=ClassificationMetrics(**test["classification"]) if test.get("classification") else None,
        validation_routing=RoutingMetrics(**val["routing"]) if val.get("routing") else None,
        test_routing=RoutingMetrics(**test["routing"]) if test.get("routing") else None,
        promotable=reason is None, not_promotable_reason=reason, pruned=pruned)
    if not detail:
        return RunSummary(**kw)
    sweep = _artifact(c, run_id, "threshold_sweep.json") or []
    return RunDetail(**kw, threshold_sweep=[ThresholdSweepPoint(**p) for p in sweep])


def predictions(run_id: str) -> PredictionsResponse:
    c = client()
    p = Path(c.download_artifacts(run_id, "predictions_test.jsonl"))
    rows = [PredictionRow(**json.loads(l)) for l in p.read_text().splitlines() if l.strip()]
    return PredictionsResponse(run_id=run_id, split="test", rows=rows)


def list_runs(experiment: str = "triagekit", limit: int = 50) -> RunListResponse:
    c = client()
    exp = c.get_experiment_by_name(experiment)
    if exp is None:
        return RunListResponse(runs=[])
    runs = c.search_runs([exp.experiment_id], order_by=["attributes.start_time DESC"], max_results=limit)
    return RunListResponse(runs=[summarize(r.info.run_id) for r in runs])


def compare(run_ids: list[str]) -> CompareResponse:
    """Runs are comparable only when evaluated on identical examples, labels, splits, contract and metric definitions."""
    summaries = [summarize(r) for r in run_ids]
    mismatches: list[str] = []
    base = summaries[0]
    if base.manifest is None:
        mismatches.append(f"{base.run_id}: missing manifest")
    for s in summaries[1:]:
        if s.manifest is None:
            mismatches.append(f"{s.run_id}: missing manifest")
            continue
        if base.manifest is None:
            continue
        for k in COMPARE_KEYS:
            a = getattr(base.manifest, k, None) if k != "metrics_version" else base.manifest.metric_definitions_version
            b = getattr(s.manifest, k, None) if k != "metrics_version" else s.manifest.metric_definitions_version
            if a != b:
                mismatches.append(f"{s.run_id}: {k} differs from {base.run_id} ({str(b)[:12]} vs {str(a)[:12]})")
    return CompareResponse(compatible=not mismatches, mismatches=mismatches, runs=summaries)
