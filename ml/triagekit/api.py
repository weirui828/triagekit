"""Internal HTTP API. Only Next.js calls this; bind to localhost. No authentication by design."""
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import __version__, jobs, prune as prune_mod, registry, runs
from .resolvers import llm_enabled, llm_model, llm_resolve
from .contract import validate_contract
from .schemas import (CompareRequest, CompareResponse, ContractValidateResponse, ErrorResponse, HealthResponse,
                      ImportValidateRequest, ImportValidateResponse, JobListResponse, JobLogsResponse, JobRecord,
                      PredictionsResponse, ProductionInfo, PromoteRequest, PromotionRecord, PruneRequest, PruneResponse,
                      RollbackRequest, RunDetail, RunListResponse, SuggestRequest, SuggestResponse,
                      ScoreBatchRequest, ScoreBatchResponse, ScoreRequest, ScoreResult, SnapshotExportRequest,
                      SnapshotExportResponse, SnapshotManifest, SplitAssignRequest, SplitAssignResponse, TrainConfig)
from .scoring import scorer
from .settings import SCHEMA_VERSION, data_dir, mlflow_uri
from .snapshot import export_snapshot, load_manifest
from .splits import assign_splits
from .validate import parse_csv, validate_rows


@asynccontextmanager
async def lifespan(app: FastAPI):
    jobs.list_jobs()  # reconcile orphaned jobs on startup
    try:
        scorer.ensure()
    except Exception as e:  # scoring stays unavailable until a model loads; do not crash the API
        print(f"model preload failed: {e}")
    yield


app = FastAPI(title="triagekit-ml", version=__version__, lifespan=lifespan,
              responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})


_STATUS = {jobs.JobBusy: 409, jobs.JobNotFound: 404, registry.NotPromotable: 409, FileExistsError: 409,
           FileNotFoundError: 404, ValueError: 400, NotImplementedError: 400, RuntimeError: 503}


async def _handled(request, exc):
    return JSONResponse(status_code=_STATUS.get(type(exc), 500), content={"error": type(exc).__name__, "detail": str(exc)})


for _cls in _STATUS:
    app.add_exception_handler(_cls, _handled)


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(ok=True, schema_version=SCHEMA_VERSION, version=__version__, mlflow_uri=mlflow_uri(), data_dir=str(data_dir()),
                          llm_enabled=llm_enabled(), llm_model=llm_model() if llm_enabled() else None)


@app.post("/contract/validate", response_model=ContractValidateResponse)
def contract_validate(body: dict):
    return validate_contract(body)


@app.post("/import/validate", response_model=ImportValidateResponse)
def import_validate(req: ImportValidateRequest):
    rows = req.rows if req.rows is not None else parse_csv(req.csv)
    return validate_rows(req.contract, rows)


@app.post("/splits/assign", response_model=SplitAssignResponse)
def splits_assign(req: SplitAssignRequest):
    return assign_splits(req.rows, req.seed, req.train_fraction, req.validation_fraction)


@app.post("/snapshots/export", response_model=SnapshotExportResponse)
def snapshots_export(req: SnapshotExportRequest):
    return export_snapshot(req)


@app.get("/snapshots/{snapshot_id}", response_model=SnapshotManifest)
def snapshot_get(snapshot_id: str):
    return load_manifest(snapshot_id)


@app.post("/jobs", response_model=JobRecord, status_code=201)
def job_start(cfg: TrainConfig):
    load_manifest(cfg.snapshot_id)
    return jobs.start_job(cfg)


@app.get("/jobs", response_model=JobListResponse)
def job_list():
    return jobs.list_jobs()


@app.get("/jobs/{job_id}", response_model=JobRecord)
def job_get(job_id: str):
    return jobs.get_job(job_id)


@app.get("/jobs/{job_id}/logs", response_model=JobLogsResponse)
def job_logs(job_id: str, offset: int = 0, limit: int = 500):
    return jobs.job_logs(job_id, offset, limit)


@app.post("/jobs/{job_id}/cancel", response_model=JobRecord)
def job_cancel(job_id: str):
    return jobs.cancel_job(job_id)


@app.get("/runs", response_model=RunListResponse)
def run_list(experiment: str = "triagekit", limit: int = 50):
    return runs.list_runs(experiment, limit)


@app.post("/runs/compare", response_model=CompareResponse)
def run_compare(req: CompareRequest):
    return runs.compare(req.run_ids)


@app.get("/runs/{run_id}/predictions", response_model=PredictionsResponse)
def run_predictions(run_id: str):
    return runs.predictions(run_id)


@app.post("/prune", response_model=PruneResponse)
def prune(req: PruneRequest):
    return prune_mod.prune(req.dry_run, req.experiment)


@app.post("/llm/suggest", response_model=SuggestResponse)
def llm_suggest(req: SuggestRequest):
    return llm_resolve(req.contract, req.text)


@app.get("/runs/{run_id}", response_model=RunDetail)
def run_get(run_id: str):
    return runs.summarize(run_id, detail=True)


@app.get("/registry/production", response_model=ProductionInfo)
def production():
    info = scorer.info()
    return ProductionInfo(model_name=registry.REGISTERED_MODEL_NAME, history=registry.history(), **info)


@app.post("/registry/promote", response_model=PromotionRecord)
def promote(req: PromoteRequest):
    rec = registry.promote(req.run_id, req.initiated_by, req.reason)
    scorer.ensure()
    return rec


@app.post("/registry/rollback", response_model=PromotionRecord)
def rollback(req: RollbackRequest):
    rec = registry.rollback(req.initiated_by, req.reason)
    scorer.ensure()
    return rec


@app.post("/score", response_model=ScoreResult)
def score(req: ScoreRequest):
    return scorer.score(req)


@app.post("/score/batch", response_model=ScoreBatchResponse)
def score_batch(req: ScoreBatchRequest):
    return scorer.score_batch(req)


def openapi_json() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True)
