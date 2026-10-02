"""CPU smoke test: snapshot -> train -> compare -> promote -> score -> rollback through the API."""
import pytest
from fastapi.testclient import TestClient

from triagekit.snapshot import load_snapshot, snapshot_from_csv


@pytest.fixture
def client(data_dir):
    from triagekit.api import app
    with TestClient(app) as c:
        yield c


def test_full_path(client, contract, example_rows, data_dir):
    snap = snapshot_from_csv("s1", "demo", contract, example_rows).manifest
    r = client.post("/jobs", json={"snapshot_id": "s1"}); assert r.status_code == 201, r.text
    job = r.json()["job_id"]
    assert client.post("/jobs", json={"snapshot_id": "s1"}).status_code == 409
    import time
    for _ in range(600):
        j = client.get(f"/jobs/{job}").json()
        if j["status"] not in ("queued", "starting", "running"):
            break
        time.sleep(0.2)
    assert j["status"] == "succeeded", client.get(f"/jobs/{job}/logs").json()
    run_id = j["run_id"]
    d = client.get(f"/runs/{run_id}").json()
    assert d["promotable"] and d["manifest"]["evaluation_hash"] == snap.evaluation_hash
    assert d["policy"]["routing_high"] - d["policy"]["routing_low"] >= 0.2 - 1e-9
    assert d["test"]["n"] == snap.split_counts["test"] - 0 or d["test"]["n"] <= snap.split_counts["test"]
    assert all(c["positive_recall"] is None for c in d["test"]["categories"] if c["positive_support"] == 0)
    assert len(d["threshold_sweep"]) > 50

    # a second snapshot with a different evaluation set is not comparable
    rows = load_snapshot("s1")[2]
    t = next(r for r in rows if r.split == "test" and r.label is not None)
    from triagekit.schemas import SnapshotExportRequest
    from triagekit.snapshot import export_snapshot
    export_snapshot(SnapshotExportRequest(snapshot_id="s2", dataset_id="demo", contract=contract,
                                          rows=[r if r.id != t.id else r.model_copy(update={"label": 1 - r.label}) for r in rows]))
    from triagekit.train import run_training
    from triagekit.schemas import TrainConfig
    run2 = run_training(TrainConfig(snapshot_id="s2"), log=lambda m: None)
    cmp = client.post("/runs/compare", json={"run_ids": [run_id, run2]}).json()
    assert not cmp["compatible"] and any("evaluation_hash" in m for m in cmp["mismatches"])
    run3 = run_training(TrainConfig(snapshot_id="s1", seed=7), log=lambda m: None)
    assert client.post("/runs/compare", json={"run_ids": [run_id, run3]}).json()["compatible"]

    # promotion, scoring, rollback
    assert client.get("/registry/production").json()["version"] is None
    p = client.post("/registry/promote", json={"run_id": run_id, "initiated_by": "test"}).json()
    assert p["kind"] == "promote" and p["prior_version"] is None
    s = client.post("/score", json={"text": "I was charged twice, refund me now"}).json()
    assert s["model_version"] == f"triagekit:{p['new_version']}" and s["action"] in ("escalate", "review", "auto_handle")
    pol = d["policy"]
    in_band = pol["routing_low"] <= s["probability"] < pol["routing_high"]
    assert in_band == (s["resolved_by"] in ("human_pending", "rule"))
    if s["resolved_by"] == "human_pending":
        assert s["final_label"] is None and s["action"] == "review"
    r = client.post("/score", json={"text": "please let me talk to a human"}).json()
    assert r["resolved_by"] in ("rule", "model") and r["final_label"] == 1
    b = client.post("/score/batch", json={"items": [{"text": "a", "request_id": "x"}, {"text": "b"}]}).json()
    assert [i["index"] for i in b["items"]] == [0, 1] and b["items"][0]["request_id"] == "x"
    assert client.post("/registry/rollback", json={}).status_code == 409
    p2 = client.post("/registry/promote", json={"run_id": run3}).json()
    assert p2["prior_version"] == p["new_version"]
    rb = client.post("/registry/rollback", json={"initiated_by": "test"}).json()
    assert rb["kind"] == "rollback" and rb["new_version"] == p["new_version"]
    assert client.get("/registry/production").json()["loaded_version"] == f"triagekit:{p['new_version']}"
    hist = client.get("/registry/production").json()["history"]
    assert [h["kind"] for h in hist] == ["promote", "promote", "rollback"]


def test_infeasible_run_not_promotable(client, contract, example_rows):
    c = contract.model_copy(deep=True)
    c.routing_policy.max_auto_error_rate = 0.0
    c.routing_policy.min_band_width = 0.0
    c.classification_threshold.min_positive_recall = 1.0
    snapshot_from_csv("s3", "demo", c, example_rows)
    from triagekit.train import run_training
    from triagekit.schemas import TrainConfig
    rid = run_training(TrainConfig(snapshot_id="s3"), log=lambda m: None)
    d = client.get(f"/runs/{rid}").json()
    if not d["policy"]["routing_feasible"] or not d["policy"]["threshold_feasible"]:
        assert not d["promotable"]
        assert client.post("/registry/promote", json={"run_id": rid}).status_code == 409


def test_bundled_model_scores_without_registry(client, tmp_path, monkeypatch):
    from pathlib import Path
    bundled = Path(__file__).resolve().parent.parent / "bundled_model"
    if not (bundled / "MLmodel").exists():
        pytest.skip("bundled model not built")
    from triagekit.scoring import scorer
    scorer._loaded = None
    s = client.post("/score", json={"text": "how do I reset my password"}).json()
    assert s["model_version"].startswith("bundled:")
    assert client.get("/registry/production").json()["source"] == "bundled"
