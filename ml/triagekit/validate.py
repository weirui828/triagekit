"""Whole-import validation. Any error means nothing is committed; the caller enforces that."""
import csv
import io
from collections import Counter
from pathlib import Path

from .schemas import (ImportValidateResponse, LabelContract, RawRow, Row, RowError, ValidationReport)

SPLITS = {"train", "validation", "test", "unassigned"}
FIELDS = ["id", "text", "label", "category", "split", "source", "group_id"]


def parse_csv(text: str) -> list[RawRow]:
    reader = csv.DictReader(io.StringIO(text))
    unknown = [c for c in (reader.fieldnames or []) if c not in FIELDS]
    if unknown:
        raise ValueError(f"unknown CSV columns: {unknown}; allowed: {FIELDS}")
    if "id" not in (reader.fieldnames or []) or "text" not in (reader.fieldnames or []):
        raise ValueError("CSV must have 'id' and 'text' columns")
    return [RawRow(**{k: (v if v not in ("", None) else None) for k, v in r.items() if k in FIELDS}) for r in reader]


def parse_csv_file(path: str | Path) -> list[RawRow]:
    return parse_csv(Path(path).read_text(encoding="utf-8"))


def validate_rows(contract: LabelContract, raw: list[RawRow]) -> ImportValidateResponse:
    errors: list[RowError] = []
    rows: list[Row] = []
    seen: Counter[str] = Counter(r.id for r in raw if r.id)
    dups = sorted(k for k, n in seen.items() if n > 1)
    allowed = set(contract.categories.allowed)
    group_splits: dict[str, set[str]] = {}
    text_splits: dict[str, set[str]] = {}

    for i, r in enumerate(raw, start=2):  # line 1 is the header
        rid = r.id.strip() if r.id else None
        err = lambda field, msg: errors.append(RowError(line=i, id=rid, field=field, message=msg))
        if not rid:
            err("id", "missing id")
        elif seen[rid] > 1:
            err("id", "duplicate id")
        text = r.text if r.text is not None else ""
        if not text.strip():
            err("text", "empty text")
        label = None
        if r.label is not None:
            s = r.label.strip()
            if s in ("0", "1"):
                label = int(s)
            elif s.lower() in ("0.0", "1.0"):
                label = int(float(s))
            else:
                err("label", f"invalid label {r.label!r}; expected 0, 1 or empty")
        cat = r.category.strip() if r.category else None
        if cat is not None and allowed and cat not in allowed:
            err("category", f"category {cat!r} not in contract categories")
        if cat is None and contract.categories.required and label is not None:
            err("category", "category is required by the contract for labeled rows")
        split = (r.split or "unassigned").strip().lower()
        if split not in SPLITS:
            err("split", f"invalid split {r.split!r}")
            split = "unassigned"
        gid = r.group_id.strip() if r.group_id else None
        if gid and split != "unassigned":
            group_splits.setdefault(gid, set()).add(split)
        if text.strip() and split != "unassigned":
            text_splits.setdefault(text.strip(), set()).add(split)
        if rid and text.strip() and seen[rid] == 1:
            rows.append(Row(id=rid, text=text, label=label, category=cat, split=split,
                            source=r.source.strip() if r.source else None, group_id=gid))

    conflicts = sorted(f"group {g}: {sorted(s)}" for g, s in group_splits.items() if len(s) > 1)
    conflicts += sorted(f"duplicate text across splits: {sorted(s)}: {t[:40]!r}" for t, s in text_splits.items() if len(s) > 1)
    for c in conflicts:
        errors.append(RowError(line=0, id=None, field="split", message=c))
    ok = not errors
    report = ValidationReport(
        ok=ok, row_count=len(raw), accepted_count=len(rows) if ok else 0,
        errors=errors[:500], duplicate_ids=dups,
        label_counts=_counts(str(r.label) if r.label is not None else "unlabeled" for r in rows),
        category_counts=_counts(r.category or "none" for r in rows),
        split_counts=_counts(r.split for r in rows),
        group_split_conflicts=conflicts,
    )
    return ImportValidateResponse(report=report, rows=rows if ok else [])


def _counts(it) -> dict[str, int]:
    return dict(sorted(Counter(it).items()))
