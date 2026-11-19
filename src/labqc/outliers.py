"""Outlier tests for laboratory data: Grubbs (one or two outliers) and Cochran (variances).

Used as in ISO 5725-2: a test statistic is compared with its critical values at the 5 % and
1 % significance levels.

    ok         not significant at 5 %
    straggler  significant at 5 % but not at 1 %: keep the value, but look for a cause
    outlier    significant at 1 %: investigate; exclude only with a technical reason

Grubbs, one value    G = max |x_i - mean| / s. Critical values from Student's t,
                     G_crit = ((n - 1) / sqrt(n)) * sqrt(t^2 / (n - 2 + t^2)),
                     t = t(1 - alpha / (2n), n - 2).
Grubbs, two values   G = S_pair / S_0, the sum of squared deviations without the two largest
                     (or two smallest) values, divided by that of all n values; small values
                     are significant. The test takes the smaller ratio of the two pairs, so
                     like the single test it is two-sided. No closed form: critical values
                     are estimated by simulation (normal samples, fixed seed) and agree with
                     published tables to about +/- 0.001.
Cochran              C = s_max^2 / sum(s_i^2) over p groups of n replicates each, testing the
                     largest variance. Critical values from the F distribution,
                     C_crit = 1 / (1 + (p - 1) / F(1 - alpha / p; n - 1, (p - 1)(n - 1))).

A test assumes the data are otherwise normal; one test at a time, and after removing a
confirmed outlier the test may be repeated on the rest.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy import stats

SIMULATIONS = 200_000
SEED = 5725


@dataclass(frozen=True)
class OutlierTest:
    """Result of one test.

    test: "grubbs", "grubbs_two" or "cochran". statistic: G or C. critical_95, critical_99:
    the critical values (for grubbs_two, the statistic is significant when *below* them).
    label: "ok", "straggler" or "outlier". suspect: the value(s) tested (for Cochran, the
    largest variance) and index: their position(s) in the input (for Cochran, the group).
    side: "high" or "low" for Grubbs, None for Cochran. n: values (Grubbs) or groups.
    """

    test: str
    statistic: float
    critical_95: float
    critical_99: float
    label: str
    suspect: tuple[float, ...]
    index: tuple[int, ...]
    side: str | None
    n: int


def _label(stat: float, c95: float, c99: float, lower_is_significant: bool = False) -> str:
    if lower_is_significant:
        return "outlier" if stat < c99 else "straggler" if stat < c95 else "ok"
    return "outlier" if stat > c99 else "straggler" if stat > c95 else "ok"


def _values(values: Sequence[float], minimum: int) -> np.ndarray:
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or x.size < minimum:
        raise ValueError(f"the test needs at least {minimum} values")
    if not np.isfinite(x).all():
        raise ValueError("every value must be a number")
    return x


def grubbs_critical(n: int, alpha: float) -> float:
    """Critical value of the single-outlier Grubbs test (two-sided) for n values."""
    if n < 3:
        raise ValueError("Grubbs needs at least 3 values")
    t = float(stats.t.ppf(1 - alpha / (2 * n), n - 2))
    return (n - 1) / math.sqrt(n) * math.sqrt(t * t / (n - 2 + t * t))


def grubbs(values: Sequence[float]) -> OutlierTest:
    """Grubbs test for one outlier: the value furthest from the mean (ISO 5725-2, 7.3.4)."""
    x = _values(values, 3)
    s = float(x.std(ddof=1))
    if s == 0:
        raise ValueError("all values are equal: there is nothing to test")
    dev = np.abs(x - x.mean())
    i = int(np.argmax(dev))
    g = float(dev[i] / s)
    c95, c99 = grubbs_critical(x.size, 0.05), grubbs_critical(x.size, 0.01)
    side = "high" if x[i] > x.mean() else "low"
    return OutlierTest("grubbs", g, c95, c99, _label(g, c95, c99), (float(x[i]),), (i,), side,
                       int(x.size))  # fmt: skip


def _pair_ratio(sorted_x: np.ndarray, low: bool) -> np.ndarray:
    """S_pair / S_0 along the last axis of sorted samples."""
    total = np.sum((sorted_x - sorted_x.mean(axis=-1, keepdims=True)) ** 2, axis=-1)
    rest = sorted_x[..., 2:] if low else sorted_x[..., :-2]
    part = np.sum((rest - rest.mean(axis=-1, keepdims=True)) ** 2, axis=-1)
    return part / total


@lru_cache(maxsize=128)
def grubbs_two_critical(n: int) -> tuple[float, float]:
    """(5 %, 1 %) lower critical values of the two-outlier Grubbs statistic, by simulation.

    The 5 % and 1 % quantiles of min(S_high / S_0, S_low / S_0) for n normal values (the
    smaller ratio of the two largest and the two smallest values), from 200 000 simulated
    samples with a fixed seed, so the values are repeatable.
    """
    if n < 4:
        raise ValueError("the two-outlier Grubbs test needs at least 4 values")
    rng = np.random.default_rng(SEED + n)
    out = []
    for start in range(0, SIMULATIONS, 20_000):
        size = min(20_000, SIMULATIONS - start)
        sample = np.sort(rng.standard_normal((size, n)), axis=1)
        out.append(np.minimum(_pair_ratio(sample, low=False), _pair_ratio(sample, low=True)))
    ratios = np.concatenate(out)
    return float(np.quantile(ratios, 0.05)), float(np.quantile(ratios, 0.01))


def grubbs_two(values: Sequence[float]) -> OutlierTest:
    """Grubbs test for two outliers: the two largest or the two smallest values, whichever
    pair gives the smaller (more significant) ratio (ISO 5725-2, 7.3.4)."""
    x = _values(values, 4)
    order = np.argsort(x, kind="stable")
    xs = x[order]
    if float(np.sum((xs - xs.mean()) ** 2)) == 0:
        raise ValueError("all values are equal: there is nothing to test")
    high = float(_pair_ratio(xs, low=False))
    low = float(_pair_ratio(xs, low=True))
    side, g, idx = ("high", high, order[-2:]) if high <= low else ("low", low, order[:2])
    c95, c99 = grubbs_two_critical(int(x.size))
    idx = tuple(sorted(int(i) for i in idx))
    return OutlierTest("grubbs_two", g, c95, c99, _label(g, c95, c99, lower_is_significant=True),
                       tuple(float(x[i]) for i in idx), idx, side, int(x.size))  # fmt: skip


def cochran_critical(p: int, n: int, alpha: float) -> float:
    """Critical value of Cochran's C for p groups of n replicates each."""
    if p < 2 or n < 2:
        raise ValueError("Cochran's test needs at least 2 groups of at least 2 replicates")
    f = float(stats.f.ppf(1 - alpha / p, n - 1, (p - 1) * (n - 1)))
    return 1 / (1 + (p - 1) / f)


def cochran(groups: Sequence[Sequence[float]]) -> OutlierTest:
    """Cochran's test for the largest variance among p groups (ISO 5725-2, 7.3.2).

    Each group is the replicate results of one laboratory, day or level; all groups need
    the same number of replicates n (at least 2).
    """
    arrays = [np.asarray(g, dtype=float) for g in groups]
    if len(arrays) < 2:
        raise ValueError("Cochran's test needs at least 2 groups")
    sizes = {a.size for a in arrays}
    if len(sizes) != 1:
        raise ValueError("every group needs the same number of replicates")
    n = sizes.pop()
    if n < 2:
        raise ValueError("every group needs at least 2 replicates")
    if not all(np.isfinite(a).all() for a in arrays):
        raise ValueError("every value must be a number")
    var = np.array([a.var(ddof=1) for a in arrays])
    if var.sum() == 0:
        raise ValueError("every group has zero spread: there is nothing to test")
    i = int(np.argmax(var))
    c = float(var[i] / var.sum())
    p = len(arrays)
    c95, c99 = cochran_critical(p, n, 0.05), cochran_critical(p, n, 0.01)
    return OutlierTest("cochran", c, c95, c99, _label(c, c95, c99), (float(var[i]),), (i,), None,
                       p)  # fmt: skip
