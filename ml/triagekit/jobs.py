"""Durable subprocess training jobs. One active job at a time; orphaned jobs are reconciled, never resumed."""
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .schemas import JobListResponse, JobLogsResponse, JobRecord, TrainConfig
from .settings import jobs_dir

ACTIVE = {"queued", "starting", "running"}


class JobBusy(Exception):
    pass


class JobNotFound(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ps_start(pid: int) -> str | None:
    try:
        out = subprocess.check_output(["ps", "-o", "lstart=", "-p", str(pid)], text=True, stderr=subprocess.DEVNULL).strip()
        return out or None
    except subprocess.CalledProcessError:
        return None


def _alive(rec: JobRecord) -> bool:
    if rec.pid is None:
        return False
    try:
        os.kill(rec.pid, 0)
    except OSError:
        return False
    start = _ps_start(rec.pid)
    return start is not None and (rec.process_start is None or start == rec.process_start)


def _read(job_id: str, root: Path) -> JobRecord:
    p = root / job_id / "job.json"
    if not p.exists():
        raise JobNotFound(job_id)
    return JobRecord.model_validate_json(p.read_text())


def _write(rec: JobRecord, root: Path) -> JobRecord:
    (root / rec.job_id / "job.json").write_text(rec.model_dump_json(indent=2))
    return rec


def reconcile(job_id: str, root: Path | None = None) -> JobRecord:
    """Re-read the record and mark jobs without a live worker as interrupted."""
    root = root or jobs_dir()
    rec = _read(job_id, root)
    if rec.status in ACTIVE and not _alive(rec):
        rec = _read(job_id, root)  # worker may have written its final status between checks
        if rec.status in ACTIVE:
            rec = _write(rec.model_copy(update={"status": "interrupted", "finished_at": _now(),
                                                "error": "worker process not found on reconcile"}), root)
    return rec


def list_jobs(root: Path | None = None) -> JobListResponse:
    root = root or jobs_dir()
    ids = sorted((d.name for d in root.iterdir() if (d / "job.json").exists()), reverse=True)
    return JobListResponse(jobs=[reconcile(i, root) for i in ids])


def active_job(root: Path | None = None) -> JobRecord | None:
    return next((j for j in list_jobs(root).jobs if j.status in ACTIVE), None)


def start_job(cfg: TrainConfig, root: Path | None = None, python: str | None = None) -> JobRecord:
    root = root or jobs_dir()
    busy = active_job(root)
    if busy:
        raise JobBusy(busy.job_id)
    job_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    d = root / job_id
    d.mkdir()
    (d / "config.json").write_text(cfg.model_dump_json(indent=2))
    rec = _write(JobRecord(job_id=job_id, config=cfg, status="queued", created_at=_now()), root)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    with open(d / "train.log", "ab") as log:
        proc = subprocess.Popen([python or sys.executable, "-m", "triagekit.worker", str(d)],
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=env)
    rec = _read(job_id, root)
    if rec.status == "queued":
        rec = rec.model_copy(update={"status": "starting"})
    return _write(rec.model_copy(update={"pid": proc.pid, "process_start": _ps_start(proc.pid)}), root)


def get_job(job_id: str, root: Path | None = None) -> JobRecord:
    return reconcile(job_id, root)


def cancel_job(job_id: str, root: Path | None = None, grace: float = 5.0) -> JobRecord:
    root = root or jobs_dir()
    rec = reconcile(job_id, root)
    if rec.status not in ACTIVE:
        return rec
    try:
        os.killpg(os.getpgid(rec.pid), signal.SIGTERM)
    except OSError:
        pass
    deadline = time.time() + grace
    while time.time() < deadline and _alive(rec):
        time.sleep(0.1)
    if _alive(rec):
        try:
            os.killpg(os.getpgid(rec.pid), signal.SIGKILL)
        except OSError:
            pass
    rec = _read(job_id, root)
    if rec.status in ACTIVE or rec.status == "interrupted":
        rec = _write(rec.model_copy(update={"status": "canceled", "finished_at": _now()}), root)
    return rec


def job_logs(job_id: str, offset: int = 0, limit: int = 500, root: Path | None = None) -> JobLogsResponse:
    root = root or jobs_dir()
    rec = reconcile(job_id, root)
    lines = (root / job_id / "train.log").read_text(errors="replace").splitlines() if (root / job_id / "train.log").exists() else []
    chunk = lines[offset: offset + limit]
    return JobLogsResponse(job_id=job_id, status=rec.status, lines=chunk, offset=offset, next_offset=offset + len(chunk))
