"""Training worker subprocess: python -m triagekit.worker <job_dir>."""
import json
import signal
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from .schemas import JobRecord, TrainConfig


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _update(job_dir: Path, only_if: set[str], **fields) -> JobRecord:
    p = job_dir / "job.json"
    rec = JobRecord.model_validate_json(p.read_text())
    if rec.status in only_if:
        rec = rec.model_copy(update=fields)
        p.write_text(rec.model_dump_json(indent=2))
    return rec


def main(argv=None) -> int:
    job_dir = Path((argv or sys.argv[1:])[0])
    cfg = TrainConfig.model_validate_json((job_dir / "config.json").read_text())
    log_f = open(job_dir / "train.log", "a", buffering=1)
    log = lambda m: (log_f.write(f"{_now()} {m}\n"), print(m, flush=True))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    _update(job_dir, {"queued", "starting"}, status="running", started_at=_now())
    try:
        from .train import run_training
        rid = run_training(cfg, job_id=job_dir.name, log=log)
        (job_dir / "result.json").write_text(json.dumps({"run_id": rid}))
        _update(job_dir, {"running"}, status="succeeded", finished_at=_now(), exit_code=0, run_id=rid)
        return 0
    except SystemExit as e:
        _update(job_dir, {"running"}, status="canceled", finished_at=_now(), exit_code=int(e.code or 0))
        raise
    except BaseException as e:
        log("".join(traceback.format_exception(e)))
        _update(job_dir, {"running"}, status="failed", finished_at=_now(), exit_code=1, error=str(e)[:2000])
        return 1
    finally:
        log_f.close()


if __name__ == "__main__":
    sys.exit(main())
