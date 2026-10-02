"""Deterministic, leakage-aware split assignment. Assignments are dataset-owned once made."""
import hashlib
from collections import defaultdict

from .schemas import Row, SplitAssignment, SplitAssignResponse


def group_key(r: Row) -> str:
    return f"g:{r.group_id}" if r.group_id else f"t:{hashlib.sha256(r.text.strip().encode()).hexdigest()[:24]}"


def assign_splits(rows: list[Row], seed: int = 42, train_fraction: float = 0.7,
                  validation_fraction: float = 0.15) -> SplitAssignResponse:
    groups: dict[str, list[Row]] = defaultdict(list)
    # Rows with the same group_id or identical text share one key so they never straddle splits.
    text_to_group: dict[str, str] = {}
    for r in rows:
        if r.group_id:
            text_to_group.setdefault(r.text.strip(), f"g:{r.group_id}")
    for r in rows:
        k = text_to_group.get(r.text.strip()) or group_key(r)
        groups[k].append(r)

    errors: list[str] = []
    fixed: dict[str, str] = {}
    for k, members in groups.items():
        supplied = {m.split for m in members if m.split != "unassigned"}
        if len(supplied) > 1:
            errors.append(f"group {k} has conflicting supplied splits {sorted(supplied)}")
        elif supplied:
            fixed[k] = supplied.pop()
    if errors:
        return SplitAssignResponse(ok=False, errors=errors, assignments=[], strategy="supplied", seed=seed, split_counts={})

    free = sorted(k for k in groups if k not in fixed)
    # Seeded order over group keys; independent of input row order.
    free.sort(key=lambda k: hashlib.sha256(f"{seed}:{k}".encode()).hexdigest())
    n = sum(len(groups[k]) for k in free)
    n_train, n_val = round(n * train_fraction), round(n * validation_fraction)
    chosen: dict[str, str] = dict(fixed)
    acc = 0
    for k in free:
        chosen[k] = "train" if acc < n_train else "validation" if acc < n_train + n_val else "test"
        acc += len(groups[k])
    strategy = "supplied" if not free else "seeded_grouped" if not fixed else "mixed"
    out = [SplitAssignment(id=r.id, split=chosen[k], group_key=k) for k, ms in groups.items() for r in ms]
    out.sort(key=lambda a: a.id)
    counts: dict[str, int] = defaultdict(int)
    for a in out:
        counts[a.split] += 1
    return SplitAssignResponse(ok=True, errors=[], assignments=out, strategy=strategy, seed=seed, split_counts=dict(sorted(counts.items())))
