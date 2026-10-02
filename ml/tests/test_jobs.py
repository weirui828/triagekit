import json
import time
from pathlib import Path

import pytest

from triagekit import jobs
from triagekit.schemas import JobRecord, TrainConfig


def _wait(job_id, root, timeout=60):
    for _ in range(timeout * 10):
        rec = jobs.get_job(job_id, root)
        if rec.status not in jobs.ACTIVE:
            return rec
        time.sleep(0.1)
    raise TimeoutError


def test_one_active_job_and_cancel(data_dir, tmp_path):
    root = tmp_path / "jobs"; root.mkdir()
    cfg = TrainConfig(snapshot_id="missing")
    # replace the worker with a sleeper so the job stays active
    fake = tmp_path / "bin"; fake.mkdir()
    py = fake / "python"
    py.write_text("#!/bin/sh\nexec sleep 30\n"); py.chmod(0o755)
    rec = jobs.start_job(cfg, root, python=str(py))
    assert rec.status == "starting" and rec.pid
    with pytest.raises(jobs.JobBusy):
        jobs.start_job(cfg, root, python=str(py))
    rec = jobs.cancel_job(rec.job_id, root)
    assert rec.status == "canceled"
    assert jobs.active_job(root) is None


def test_dead_worker_marked_interrupted(data_dir, tmp_path):
    root = tmp_path / "jobs"; (root / "j1").mkdir(parents=True)
    rec = JobRecord(job_id="j1", config=TrainConfig(snapshot_id="x"), status="running", created_at="t", pid=999999, process_start="never")
    (root / "j1" / "job.json").write_text(rec.model_dump_json())
    assert jobs.get_job("j1", root).status == "interrupted"
    # a pid that exists but belongs to a different process (start time mismatch) is also dead
    import os
    rec = rec.model_copy(update={"status": "running", "pid": os.getpid(), "process_start": "Thu Jan  1 00:00:00 1970"})
    (root / "j1" / "job.json").write_text(rec.model_dump_json())
    assert jobs.get_job("j1", root).status == "interrupted"


def test_failed_job_records_error(data_dir, tmp_path):
    root = tmp_path / "jobs"; root.mkdir()
    rec = jobs.start_job(TrainConfig(snapshot_id="does-not-exist"), root)
    rec = _wait(rec.job_id, root)
    assert rec.status == "failed" and rec.exit_code == 1 and rec.run_id is None
    assert "does-not-exist" in "\n".join(jobs.job_logs(rec.job_id, root=root).lines)
