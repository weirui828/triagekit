import os
from pathlib import Path

import pytest

from triagekit.adapters.twcs import load_labeled_twcs, original_protocol_splits, split_hashes, write_canonical_csv
from triagekit.contract import load_contract_file, validate_contract
from triagekit.replicate import MANIFEST, load_manifest
from triagekit.schemas import TrainConfig
from triagekit.validate import parse_csv_file, validate_rows

TWCS = os.environ.get("TRIAGEKIT_TWCS_CSV", str(Path.home() / "dev/human-loop/data/twcs/llm_labeled_5k.csv"))


def test_adapter_roundtrip(tmp_path):
    src = tmp_path / "twcs.csv"
    src.write_text('thread_id,escalated,category,reason,labeler,turn_count,first_customer_text\n'
                   'T1,1,complaint,r,llm-x,3,"worst service, ever"\nT2,0,self_service,r,llm-x,2,where is my order\n')
    rows = load_labeled_twcs(src)
    assert [r.id for r in rows] == ["T1", "T2"] and rows[0].label == 1 and rows[0].source == "llm:llm-x" and rows[0].group_id == "T1"
    out = tmp_path / "canon.csv"
    write_canonical_csv(rows, out)
    contract = validate_contract(load_contract_file(Path(__file__).resolve().parent.parent / "examples" / "twcs.contract.yaml")).contract
    res = validate_rows(contract, parse_csv_file(out))
    assert res.report.ok and res.report.label_counts == {"0": 1, "1": 1}


def test_twcs_contract_is_valid_and_fixed_threshold():
    c = validate_contract(load_contract_file(Path(__file__).resolve().parent.parent / "examples" / "twcs.contract.yaml"))
    assert c.ok and c.contract.classification_threshold.objective == "fixed" and c.contract.classification_threshold.fixed_threshold == 0.5


def test_train_config_params_follow_model():
    assert TrainConfig(snapshot_id="s", model="distilbert").params.checkpoint == "distilbert-base-uncased"
    assert TrainConfig(snapshot_id="s", model="distilbert", params={"epochs": 1}).params.epochs == 1
    assert TrainConfig(snapshot_id="s").params.ngram_max == 2
    with pytest.raises(ValueError):
        TrainConfig(snapshot_id="s", model="distilbert", params={"ngram_max": 3})


@pytest.mark.skipif(not Path(TWCS).exists(), reason="original llm_labeled_5k.csv not available")
def test_original_split_matches_manifest():
    m = load_manifest()
    rows = load_labeled_twcs(TWCS)
    assert len(rows) == m["dataset"]["rows"]
    h = split_hashes(original_protocol_splits(rows))
    for k, v in h.items():
        assert v == m["split"][k], k
    assert MANIFEST.exists()
