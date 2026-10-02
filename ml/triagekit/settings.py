import os
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

SCHEMA_VERSION = "1"
REGISTERED_MODEL_NAME = "triagekit"
PRODUCTION_ALIAS = "production"


def data_dir() -> Path:
    p = Path(os.environ.get("TRIAGEKIT_DATA_DIR", "./data")).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def snapshots_dir() -> Path:
    return _sub("snapshots")


def jobs_dir() -> Path:
    return _sub("jobs")


def registry_dir() -> Path:
    return _sub("registry")


def mlflow_uri() -> str:
    return os.environ.get("MLFLOW_TRACKING_URI") or f"sqlite:///{data_dir() / 'mlflow.db'}"


def mlflow_artifact_root() -> str:
    return os.environ.get("MLFLOW_ARTIFACT_ROOT") or str(_sub("mlruns"))


def bundled_model_dir() -> Path:
    env = os.environ.get("TRIAGEKIT_BUNDLED_MODEL")
    return Path(env) if env else Path(__file__).resolve().parent.parent / "bundled_model"


def _sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p
