"""Adapter for the LLM-labeled TWCS sample produced by the human-loop project (llm_labeled_5k.csv)."""
import csv
import hashlib
from pathlib import Path

from ..schemas import Row

csv.field_size_limit(10**9)
REQUIRED = {"thread_id", "escalated", "first_customer_text"}
ESCALATE_CATEGORIES = ["contact_human_agent", "contact_customer_service", "complaint", "payment_issue", "get_refund",
                       "check_cancellation_fee", "registration_problems"]
CATEGORIES = ESCALATE_CATEGORIES + ["self_service"]


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_labeled_twcs(path: str | Path) -> list[Row]:
    """File order is preserved: the original split protocol depends on it."""
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"TWCS file lacks columns {sorted(missing)}")
        rows = []
        for r in reader:
            lab = r["escalated"].strip()
            if lab not in ("0", "1"):
                raise ValueError(f"thread {r['thread_id']}: invalid escalated value {lab!r}")
            labeler = (r.get("labeler") or "").strip()
            rows.append(Row(id=r["thread_id"].strip(), text=(r["first_customer_text"] or ""), label=int(lab),
                            category=(r.get("category") or "").strip() or None, split="unassigned",
                            source=f"llm:{labeler}" if labeler else "twcs", group_id=r["thread_id"].strip()))
    return rows


def original_protocol_splits(rows: list[Row], seed: int = 42, test_size: float = 0.20, val_size: float = 0.10) -> dict[str, str]:
    """human-loop notebook 04: stratified 80/20 on file order, then stratified 90/10 of the training part."""
    from sklearn.model_selection import train_test_split
    ids = [r.id for r in rows]
    y = [r.label for r in rows]
    tr_full, te, y_tr_full, _ = train_test_split(ids, y, test_size=test_size, random_state=seed, stratify=y)
    if val_size:
        tr, va, _, _ = train_test_split(tr_full, y_tr_full, test_size=val_size, random_state=seed, stratify=y_tr_full)
    else:
        tr, va = tr_full, []
    out = {i: "train" for i in tr}
    out.update({i: "validation" for i in va})
    out.update({i: "test" for i in te})
    return out


def ids_sha256(ids) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def split_hashes(assign: dict[str, str]) -> dict[str, str]:
    return {f"{s}_ids_sha256": ids_sha256([i for i, v in assign.items() if v == s]) for s in ("train", "validation", "test")} | {
        "split_manifest_sha256": hashlib.sha256("\n".join(f"{i}\t{s}" for i, s in sorted(assign.items())).encode()).hexdigest()}


def write_canonical_csv(rows: list[Row], out: str | Path) -> None:
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "text", "label", "category", "split", "source", "group_id"])
        w.writeheader()
        for r in rows:
            w.writerow({"id": r.id, "text": r.text, "label": "" if r.label is None else r.label, "category": r.category or "",
                        "split": r.split, "source": r.source or "", "group_id": r.group_id or ""})
