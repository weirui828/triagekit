import pytest

from triagekit.schemas import SnapshotExportRequest
from triagekit.snapshot import export_snapshot, load_snapshot, snapshot_from_csv


def test_snapshot_is_immutable_and_hashes_stable(data_dir, contract, example_rows):
    a = snapshot_from_csv("s1", "d", contract, example_rows)
    assert a.created
    rows = load_snapshot("s1")[2]
    same = export_snapshot(SnapshotExportRequest(snapshot_id="s1", dataset_id="d", contract=contract, rows=rows))
    assert not same.created and same.manifest.snapshot_hash == a.manifest.snapshot_hash
    changed = [rows[0].model_copy(update={"label": 1 - (rows[0].label or 0)})] + rows[1:]
    with pytest.raises(FileExistsError):
        export_snapshot(SnapshotExportRequest(snapshot_id="s1", dataset_id="d", contract=contract, rows=changed))
    with pytest.raises(PermissionError):
        (data_dir / "snapshots" / "s1" / "rows.jsonl").write_text("tamper")


def test_training_hash_ignores_eval_changes_and_vice_versa(data_dir, contract, example_rows):
    base = snapshot_from_csv("s1", "d", contract, example_rows).manifest
    rows = load_snapshot("s1")[2]
    test_row = next(r for r in rows if r.split == "test" and r.label is not None)
    flipped = [r if r.id != test_row.id else r.model_copy(update={"label": 1 - r.label}) for r in rows]
    m = export_snapshot(SnapshotExportRequest(snapshot_id="s2", dataset_id="d", contract=contract, rows=flipped)).manifest
    assert m.training_data_hash == base.training_data_hash
    assert m.evaluation_hash != base.evaluation_hash
    assert m.split_manifest_hash == base.split_manifest_hash
    unlabeled = [r for r in rows if r.label is None]
    assert unlabeled, "example data should contain unlabeled rows"
    assert all(r.split != "unassigned" for r in rows)  # every row has a split, but unlabeled rows stay out of hashes
