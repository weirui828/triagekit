import numpy as np

from triagekit.evaluate import classification_metrics, routing_metrics
from triagekit.policy import select_policy, select_routing


def test_threshold_selected_on_validation_only(contract):
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 200)
    p = np.clip(y * 0.6 + rng.normal(0.2, 0.15, 200), 0, 1)
    sel1, _ = select_policy(y, p, contract)
    sel2, _ = select_policy(y, p, contract)
    assert sel1 == sel2
    # test labels are never an input: selection signature takes only validation arrays
    assert sel1.threshold_feasible and 0.05 <= sel1.classification_threshold <= 0.95


def test_min_band_width_forces_review_band(contract):
    y = np.array([0] * 20 + [1] * 20)
    p = np.array([0.1] * 20 + [0.9] * 20)  # perfect separation
    lo, hi, ok, _ = select_routing(y, p, 0.5, contract)
    assert ok and hi - lo >= contract.routing_policy.min_band_width - 1e-9
    c2 = contract.model_copy(deep=True)
    c2.routing_policy.min_band_width = 0.0
    lo, hi, ok, _ = select_routing(y, p, 0.5, c2)
    assert ok and lo == hi == 0.5


def test_infeasible_constraints_reported(contract):
    y = np.array([0, 1] * 20)
    p = np.array([0.5] * 40)  # model is useless
    c = contract.model_copy(deep=True)
    c.routing_policy.max_auto_error_rate = 0.01
    lo, hi, ok, notes = select_routing(y, p, 0.5, c)
    assert not ok and (lo, hi) == (0.0, 1.0) and notes


def test_undefined_metrics_are_null():
    m = classification_metrics(np.array([0, 0]), np.array([0.1, 0.2]), 0.5, ["a", "b"])
    assert m.positive_precision is None and m.positive_recall is None and m.macro_f1 is None
    assert all(c.positive_recall is None and c.positive_support == 0 for c in m.categories)
    r = routing_metrics(np.array([0, 0]), np.array([0.1, 0.2]), 0.5, 0.3, 0.7)
    assert r.missed_positive_rate is None and r.errors_captured_by_band is None


def test_routing_boundaries_are_half_open():
    y = np.array([0, 1, 1]); p = np.array([0.29, 0.3, 0.7])
    r = routing_metrics(y, p, 0.5, 0.3, 0.7)
    assert r.auto_decided == 2 and r.review_count == 1  # 0.29 auto, 0.3 review, 0.7 escalate
