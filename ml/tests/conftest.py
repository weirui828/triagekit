import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "data"
    monkeypatch.setenv("TRIAGEKIT_DATA_DIR", str(d))
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("MLFLOW_ARTIFACT_ROOT", raising=False)
    return d


@pytest.fixture
def contract():
    from triagekit.contract import load_contract_file, validate_contract
    return validate_contract(load_contract_file(ROOT / "examples" / "support_demo.contract.yaml")).contract


@pytest.fixture
def example_rows(contract):
    from triagekit.validate import parse_csv_file, validate_rows
    res = validate_rows(contract, parse_csv_file(ROOT / "examples" / "support_demo.csv"))
    assert res.report.ok
    return res.rows
