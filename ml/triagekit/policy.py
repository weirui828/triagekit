"""Threshold and routing-bound selection. Callers must pass validation data only."""
import numpy as np

from .evaluate import routing_metrics, threshold_sweep
from .schemas import LabelContract, PolicySelection, ThresholdSweepPoint


def select_threshold(sweep: list[ThresholdSweepPoint], contract: LabelContract) -> tuple[float, bool, list[str]]:
    pol = contract.classification_threshold
    if pol.objective == "fixed":
        t = float(pol.fixed_threshold)
        pt = next((p for p in sweep if abs(p.threshold - t) < 1e-9), None)
        notes = [f"threshold fixed at {t} by contract"]
        ok = True
        if pol.min_positive_recall is not None and pt is not None and (pt.positive_recall or 0.0) < pol.min_positive_recall:
            ok, notes = False, notes + [f"fixed threshold misses min_positive_recall={pol.min_positive_recall} on validation"]
        return t, ok, notes
    key = {"max_macro_f1": lambda p: p.macro_f1, "max_positive_f1": lambda p: p.positive_f1}[pol.objective]
    cands = [p for p in sweep if key(p) is not None]
    notes: list[str] = []
    feasible = True
    if pol.min_positive_recall is not None:
        ok = [p for p in cands if p.positive_recall is not None and p.positive_recall >= pol.min_positive_recall]
        if ok:
            cands = ok
        else:
            feasible = False
            notes.append(f"no threshold reaches min_positive_recall={pol.min_positive_recall} on validation")
    if not cands:
        return 0.5, False, notes + ["threshold objective undefined on validation data; defaulting to 0.5"]
    best = max(cands, key=lambda p: (key(p), -abs(p.threshold - 0.5)))
    return best.threshold, feasible, notes


def select_routing(y: np.ndarray, prob: np.ndarray, threshold: float, contract: LabelContract,
                   step: float = 0.05) -> tuple[float, float, bool, list[str]]:
    pol = contract.routing_policy
    lows = [round(x, 2) for x in np.arange(0.0, threshold + 1e-9, step)] + [threshold]
    highs = [threshold] + [round(x, 2) for x in np.arange(threshold, 1.0 + 1e-9, step)] + [1.0]
    best = None
    for lo in sorted(set(lows)):
        for hi in sorted(set(highs)):
            if not (lo <= threshold <= hi) or (hi - lo) + 1e-9 < pol.min_band_width:
                continue
            m = routing_metrics(y, prob, threshold, lo, hi)
            if m.auto_decided == 0:
                continue  # vacuously satisfies constraints; not a usable policy
            if pol.max_auto_error_rate is not None and (m.auto_error_rate or 0.0) > pol.max_auto_error_rate:
                continue
            if pol.max_missed_positive_rate is not None and (m.missed_positive_rate or 0.0) > pol.max_missed_positive_rate:
                continue
            cand = (m.coverage or 0.0, -(hi - lo), lo, hi)
            if best is None or cand > best:
                best = cand
    if best is None:
        return 0.0, 1.0, False, ["no routing bounds satisfy the contract constraints on validation; everything routes to review"]
    _, _, lo, hi = best
    return lo, hi, True, []


def select_policy(y_val: np.ndarray, prob_val: np.ndarray, contract: LabelContract) -> tuple[PolicySelection, list[ThresholdSweepPoint]]:
    sweep = threshold_sweep(y_val, prob_val, include=contract.classification_threshold.fixed_threshold)
    t, t_ok, notes = select_threshold(sweep, contract)
    lo, hi, r_ok, rnotes = select_routing(y_val, prob_val, t, contract)
    sel = PolicySelection(classification_threshold=t, threshold_objective=contract.classification_threshold.objective,
                          threshold_feasible=t_ok, routing_low=lo, routing_high=hi,
                          routing_objective=contract.routing_policy.objective, routing_feasible=r_ok, notes=notes + rnotes)
    return sel, sweep
