"""Immutable snapshot exports on the shared volume. Hashes are computed here and only here."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .contract import contract_hash
from .hashing import canonical_json, sha256_text
from .schemas import (LabelContract, PreprocessingConfig, Row, SnapshotExportRequest,
                      SnapshotExportResponse, SnapshotManifest)
from .settings import snapshots_dir


def _row_line(r: Row) -> str:
    return canonical_json(r.model_dump(mode="json"))


def compute_hashes(rows: list[Row]) -> dict[str, str]:
    ordered = sorted(rows, key=lambda r: r.id)
    train = [r for r in ordered if r.split == "train" and r.label is not None]
    evalrows = [r for r in ordered if r.split in ("validation", "test") and r.label is not None]
    return {
        "rows_hash": sha256_text("\n".join(_row_line(r) for r in ordered)),
        "training_data_hash": sha256_text("\n".join(f"{r.id}\t{r.label}\t{r.text}" for r in train)),
        "split_manifest_hash": sha256_text("\n".join(f"{r.id}\t{r.split}" for r in ordered)),
        "evaluation_hash": sha256_text("\n".join(f"{r.id}\t{r.split}\t{r.label}\t{r.text}" for r in evalrows)),
    }


def export_snapshot(req: SnapshotExportRequest, root: Path | None = None) -> SnapshotExportResponse:
    root = root or snapshots_dir()
    dest = root / req.snapshot_id
    rows = sorted(req.rows, key=lambda r: r.id)
    h = compute_hashes(rows)
    c_hash = contract_hash(req.contract)
    content_hash = sha256_text(canonical_json({**h, "contract_hash": c_hash,
                                               "preprocessing": req.preprocessing.model_dump(mode="json")}))
    if dest.exists():
        existing = load_manifest(req.snapshot_id, root)
        if existing.snapshot_hash != content_hash:
            raise FileExistsError(f"snapshot {req.snapshot_id} exists with different content; snapshots are immutable")
        return SnapshotExportResponse(manifest=existing, created=False)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.split] = counts.get(r.split, 0) + 1
    manifest = SnapshotManifest(
        snapshot_id=req.snapshot_id, dataset_id=req.dataset_id,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        contract_version=req.contract.contract_version, contract_hash=c_hash,
        preprocessing=req.preprocessing, row_count=len(rows),
        labeled_count=sum(r.label is not None for r in rows), split_counts=dict(sorted(counts.items())),
        snapshot_hash=content_hash, path=str(dest), **h,
    )
    tmp = Path(tempfile.mkdtemp(prefix=f".{req.snapshot_id}.", dir=root))
    (tmp / "rows.jsonl").write_text("\n".join(_row_line(r) for r in rows) + "\n")
    (tmp / "contract.json").write_text(canonical_json(req.contract.model_dump(mode="json")))
    (tmp / "manifest.json").write_text(json.dumps(manifest.model_dump(mode="json"), indent=2))
    for p in tmp.iterdir():
        p.chmod(0o444)
    os.rename(tmp, dest)  # atomic publish: no partially written snapshot is ever visible
    return SnapshotExportResponse(manifest=manifest, created=True)


def load_manifest(snapshot_id: str, root: Path | None = None) -> SnapshotManifest:
    root = root or snapshots_dir()
    return SnapshotManifest.model_validate_json((root / snapshot_id / "manifest.json").read_text())


def load_snapshot(snapshot_id: str, root: Path | None = None) -> tuple[SnapshotManifest, LabelContract, list[Row]]:
    root = root or snapshots_dir()
    d = root / snapshot_id
    manifest = load_manifest(snapshot_id, root)
    contract = LabelContract.model_validate_json((d / "contract.json").read_text())
    rows = [Row.model_validate_json(line) for line in (d / "rows.jsonl").read_text().splitlines() if line.strip()]
    if compute_hashes(rows)["rows_hash"] != manifest.rows_hash:
        raise ValueError(f"snapshot {snapshot_id} rows do not match manifest hash")
    return manifest, contract, rows


def snapshot_from_csv(snapshot_id: str, dataset_id: str, contract: LabelContract, rows: list[Row],
                      preprocessing: PreprocessingConfig | None = None, seed: int = 42, keep_splits: bool = False) -> SnapshotExportResponse:
    """CLI convenience: assign splits (unless supplied and kept) then export."""
    if keep_splits:
        missing = [r.id for r in rows if r.split == "unassigned"]
        if missing:
            raise ValueError(f"--keep-splits requires every row to have a split; {len(missing)} unassigned")
    else:
        from .splits import assign_splits
        res = assign_splits(rows, seed=seed)
        if not res.ok:
            raise ValueError("; ".join(res.errors))
        by_id = {a.id: a.split for a in res.assignments}
        rows = [r.model_copy(update={"split": by_id[r.id]}) for r in rows]
    return export_snapshot(SnapshotExportRequest(snapshot_id=snapshot_id, dataset_id=dataset_id, contract=contract,
                                                 preprocessing=preprocessing or PreprocessingConfig(), rows=rows))
