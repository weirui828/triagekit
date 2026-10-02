from triagekit.schemas import RawRow
from triagekit.validate import parse_csv, validate_rows


def test_any_error_rejects_whole_import(contract):
    rows = [RawRow(id="a", text="hello", label="1"), RawRow(id="b", text="  ", label="0"), RawRow(id="a", text="dup", label="x")]
    res = validate_rows(contract, rows)
    assert not res.report.ok
    assert res.rows == [] and res.report.accepted_count == 0
    msgs = {(e.id, e.field) for e in res.report.errors}
    assert ("b", "text") in msgs and ("a", "id") in msgs and ("a", "label") in msgs
    assert res.report.duplicate_ids == ["a"]


def test_category_and_split_checks(contract):
    rows = [RawRow(id="1", text="x", label="0", category="nope"), RawRow(id="2", text="y", split="dev")]
    errs = validate_rows(contract, rows).report.errors
    assert {e.field for e in errs} == {"category", "split"}


def test_group_split_conflict_rejected(contract):
    rows = [RawRow(id="1", text="a", label="0", split="train", group_id="g"),
            RawRow(id="2", text="b", label="1", split="test", group_id="g")]
    rep = validate_rows(contract, rows).report
    assert not rep.ok and rep.group_split_conflicts


def test_duplicate_text_across_splits_rejected(contract):
    rows = [RawRow(id="1", text="same", label="0", split="train"), RawRow(id="2", text="same", label="0", split="test")]
    assert not validate_rows(contract, rows).report.ok


def test_parse_csv_rejects_unknown_columns():
    import pytest
    with pytest.raises(ValueError):
        parse_csv("id,text,foo\n1,a,b\n")
    assert parse_csv("id,text,label\n1,hi,\n")[0].label is None


def test_counts_use_accepted_rows(contract):
    res = validate_rows(contract, [RawRow(id="1", text="a", label="1", category="billing"), RawRow(id="2", text="b")])
    assert res.report.label_counts == {"1": 1, "unlabeled": 1}
    assert res.report.category_counts == {"billing": 1, "none": 1}
