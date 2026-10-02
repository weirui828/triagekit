from triagekit.schemas import Row
from triagekit.splits import assign_splits


def _rows(n, **kw):
    return [Row(id=f"r{i}", text=f"text {i}", label=i % 2, **kw) for i in range(n)]


def test_deterministic_and_order_independent():
    rows = _rows(100)
    a = assign_splits(rows, seed=1).assignments
    b = assign_splits(list(reversed(rows)), seed=1).assignments
    assert a == b
    assert assign_splits(rows, seed=2).assignments != a


def test_groups_and_duplicate_texts_never_straddle():
    rows = [Row(id=f"g{i}", text=f"t{i}", label=0, group_id=f"grp{i % 5}") for i in range(50)]
    rows += [Row(id=f"d{i}", text="identical", label=1) for i in range(10)]
    res = assign_splits(rows)
    by_id = {a.id: a.split for a in res.assignments}
    for g in range(5):
        assert len({by_id[f"g{i}"] for i in range(50) if i % 5 == g}) == 1
    assert len({by_id[f"d{i}"] for i in range(10)}) == 1


def test_supplied_splits_preserved_and_conflicts_rejected():
    rows = _rows(20)
    rows[0] = rows[0].model_copy(update={"split": "test"})
    res = assign_splits(rows)
    assert res.ok and res.strategy == "mixed"
    assert {a.id: a.split for a in res.assignments}["r0"] == "test"
    bad = [Row(id="1", text="a", split="train", group_id="g"), Row(id="2", text="b", split="test", group_id="g")]
    assert not assign_splits(bad).ok


def test_fractions_respected_roughly():
    res = assign_splits(_rows(200), train_fraction=0.6, validation_fraction=0.2)
    assert 110 <= res.split_counts["train"] <= 130
