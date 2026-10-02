"""Explicit promotion/rollback against a pinned MLflow registry alias."""
import json
import uuid
from datetime import datetime, timezone

from mlflow import MlflowException

from .runs import client, summarize
from .schemas import ProductionInfo, PromotionRecord
from .settings import PRODUCTION_ALIAS, REGISTERED_MODEL_NAME, registry_dir


class NotPromotable(Exception):
    pass


def _log_path():
    return registry_dir() / "promotions.jsonl"


def history() -> list[PromotionRecord]:
    p = _log_path()
    if not p.exists():
        return []
    return [PromotionRecord.model_validate_json(l) for l in p.read_text().splitlines() if l.strip()]


def _append(rec: PromotionRecord) -> PromotionRecord:
    with open(_log_path(), "a") as f:
        f.write(rec.model_dump_json() + "\n")
    return rec


def current_version() -> tuple[str | None, str | None]:
    """(version, run_id) for the production alias, or (None, None)."""
    try:
        mv = client().get_model_version_by_alias(REGISTERED_MODEL_NAME, PRODUCTION_ALIAS)
        return str(mv.version), mv.run_id
    except MlflowException:
        return None, None


def model_uri() -> str:
    return f"models:/{REGISTERED_MODEL_NAME}@{PRODUCTION_ALIAS}"


def promote(run_id: str, initiated_by: str = "api", reason: str | None = None) -> PromotionRecord:
    s = summarize(run_id)
    if not s.promotable:
        raise NotPromotable(s.not_promotable_reason or "not promotable")
    c = client()
    try:
        c.get_registered_model(REGISTERED_MODEL_NAME)
    except MlflowException:
        c.create_registered_model(REGISTERED_MODEL_NAME)
    existing = [mv for mv in c.search_model_versions(f"name='{REGISTERED_MODEL_NAME}' and run_id='{run_id}'")]
    source = c.get_run(run_id).data.tags.get("triagekit.model_uri") or f"runs:/{run_id}/model"
    version = str(existing[0].version) if existing else str(c.create_model_version(REGISTERED_MODEL_NAME, source, run_id).version)
    prior, _ = current_version()
    c.set_registered_model_alias(REGISTERED_MODEL_NAME, PRODUCTION_ALIAS, version)
    return _append(PromotionRecord(event_id=uuid.uuid4().hex, kind="promote", at=_now(), initiated_by=initiated_by,
                                   reason=reason, prior_version=prior, new_version=version, run_id=run_id))


def rollback(initiated_by: str = "api", reason: str | None = None) -> PromotionRecord:
    h = history()
    cur, _ = current_version()
    target = next((r.prior_version for r in reversed(h) if r.new_version == cur and r.prior_version), None)
    if target is None:
        raise NotPromotable("no prior promoted version to roll back to")
    target = str(target)
    c = client()
    mv = c.get_model_version(REGISTERED_MODEL_NAME, target)
    if summarize(mv.run_id).pruned:
        raise NotPromotable(f"prior version {target} was pruned")
    c.set_registered_model_alias(REGISTERED_MODEL_NAME, PRODUCTION_ALIAS, target)
    return _append(PromotionRecord(event_id=uuid.uuid4().hex, kind="rollback", at=_now(), initiated_by=initiated_by,
                                   reason=reason, prior_version=cur, new_version=target, run_id=mv.run_id))


def protected_versions() -> set[str]:
    """Current production plus every previously promoted version (rollback targets)."""
    cur, _ = current_version()
    return {r.new_version for r in history()} | ({cur} if cur else set())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
