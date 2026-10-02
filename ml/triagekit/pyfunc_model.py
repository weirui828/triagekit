"""MLflow pyfunc packaging: model weights + preprocessing + thresholds + routing bounds + contract."""
import json
from pathlib import Path

import mlflow.pyfunc

from .schemas import LabelContract, PolicySelection

ARTIFACT_KEY = "package"


class TriagePyfunc(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        from .models.base import load_model
        root = Path(context.artifacts[ARTIFACT_KEY])
        self.package = json.loads((root / "package.json").read_text())
        self.policy = PolicySelection(**self.package["policy"])
        self.contract = LabelContract(**self.package["contract"])
        self.model = load_model(self.package["model_kind"], root / "weights")

    def predict(self, context, model_input: list[str], params=None) -> list[dict]:
        probs = self.model.predict_proba([str(t) for t in model_input])
        return [{"probability": float(p)} for p in probs]


def write_package(root: Path, model, policy: PolicySelection, contract: LabelContract, extra: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    model.save(root / "weights")
    (root / "package.json").write_text(json.dumps({
        "model_kind": model.kind, "policy": policy.model_dump(mode="json"),
        "contract": contract.model_dump(mode="json"), **extra}, indent=2))
    return root


def load_package(model_uri: str) -> tuple[mlflow.pyfunc.PyFuncModel, dict]:
    m = mlflow.pyfunc.load_model(model_uri)
    return m, m.unwrap_python_model().package
