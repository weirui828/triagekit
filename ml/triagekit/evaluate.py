"""Metric definitions. Undefined ratios are None, never 0. METRICS_VERSION changes when definitions change."""
from collections import defaultdict

import numpy as np

from .schemas import (CategoryMetrics, ClassificationMetrics, ConfusionMatrix, RoutingMetrics,
                      ThresholdSweepPoint)

METRICS_VERSION = "1"


def _div(a: float, b: float) -> float | None:
    return a / b if b else None


def _prf(tp: int, fp: int, fn: int) -> tuple[float | None, float | None, float | None]:
    p, r = _div(tp, tp + fp), _div(tp, tp + fn)
    f = None if p is None or r is None else _div(2 * p * r, p + r) if (p + r) else 0.0
    return p, r, f


def macro_f1(y: np.ndarray, pred: np.ndarray) -> float | None:
    fs = []
    for cls in (0, 1):
        tp = int(((pred == cls) & (y == cls)).sum())
        fp = int(((pred == cls) & (y != cls)).sum())
        fn = int(((pred != cls) & (y == cls)).sum())
        _, _, f = _prf(tp, fp, fn)
        fs.append(f)
    if any(f is None for f in fs):
        return None
    return float(np.mean(fs))


def classification_metrics(y: np.ndarray, prob: np.ndarray, threshold: float,
                           categories: list[str | None] | None = None) -> ClassificationMetrics:
    pred = (prob >= threshold).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
    p, r, f = _prf(tp, fp, fn)
    cats: list[CategoryMetrics] = []
    if categories is not None:
        idx: dict[str, list[int]] = defaultdict(list)
        for i, c in enumerate(categories):
            idx[c or "none"].append(i)
        for c in sorted(idx):
            ii = np.array(idx[c])
            pos = ii[y[ii] == 1]
            cats.append(CategoryMetrics(
                category=c, count=len(ii), positive_support=len(pos),
                positive_recall=_div(int((pred[pos] == 1).sum()), len(pos)),
                accuracy=_div(int((pred[ii] == y[ii]).sum()), len(ii))))
    return ClassificationMetrics(
        n=len(y), macro_f1=macro_f1(y, pred), positive_precision=p, positive_recall=r, positive_f1=f,
        accuracy=_div(tp + tn, len(y)), confusion=ConfusionMatrix(tn=tn, fp=fp, fn=fn, tp=tp), categories=cats)


def threshold_sweep(y: np.ndarray, prob: np.ndarray, grid: np.ndarray | None = None, include: float | None = None) -> list[ThresholdSweepPoint]:
    grid = np.round(np.arange(0.05, 0.96, 0.01), 2) if grid is None else grid
    if include is not None and not np.any(np.isclose(grid, include)):
        grid = np.sort(np.append(grid, include))
    out = []
    for t in grid:
        m = classification_metrics(y, prob, float(t))
        out.append(ThresholdSweepPoint(threshold=float(t), macro_f1=m.macro_f1, positive_precision=m.positive_precision,
                                       positive_recall=m.positive_recall, positive_f1=m.positive_f1))
    return out


def routing_metrics(y: np.ndarray, prob: np.ndarray, threshold: float, low: float, high: float) -> RoutingMetrics:
    pred = (prob >= threshold).astype(int)
    auto = (prob < low) | (prob >= high)
    band = ~auto
    auto_pred = np.where(prob >= high, 1, 0)
    auto_err = int((auto & (auto_pred != y)).sum())
    positives = int((y == 1).sum())
    pos_auto_handled = int(((prob < low) & (y == 1)).sum())
    model_err = pred != y
    return RoutingMetrics(
        n=len(y), low=low, high=high, auto_decided=int(auto.sum()), coverage=_div(int(auto.sum()), len(y)),
        auto_errors=auto_err, auto_error_rate=_div(auto_err, int(auto.sum())),
        positives_total=positives, positives_auto_handled=pos_auto_handled,
        missed_positive_rate=_div(pos_auto_handled, positives),
        model_errors_total=int(model_err.sum()), model_errors_in_band=int((model_err & band).sum()),
        errors_captured_by_band=_div(int((model_err & band).sum()), int(model_err.sum())),
        review_count=int(band.sum()))
