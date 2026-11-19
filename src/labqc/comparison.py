"""Method comparison: two methods (or instruments) measure the same samples.

Bland-Altman  The differences d = y - x against the means (x + y) / 2. The bias is the mean
              difference and the 95 % limits of agreement are bias -/+ 1.96 s_d, where most
              differences between the methods fall (Bland & Altman, Lancet 1986). Confidence
              intervals: bias -/+ t s_d / sqrt(n); each limit -/+ t s_d sqrt(3 / n).
Deming        A straight line y = a + b x when both methods have random error, with
              `error_ratio` = var(error of y) / var(error of x) (1 when both are equally
              precise; it is then orthogonal regression). Confidence intervals of a and b by
              the jackknife (Linnet, Clin. Chem. 1990), with n - 2 degrees of freedom.
Passing-Bablok A line from the shifted median of all pairwise slopes; robust to outliers and
              free of distribution assumptions (Passing & Bablok, J. Clin. Chem. Clin.
              Biochem. 1983). Rank-based 95 % confidence intervals, and the cusum test for
              linearity from the same paper.

Agreement: the line is consistent with y = x when the interval of the slope contains 1 and
that of the intercept contains 0.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats


def _pairs(x: Sequence[float], y: Sequence[float], minimum: int) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(x, dtype=float)
    b = np.asarray(y, dtype=float)
    if a.ndim != 1 or a.shape != b.shape:
        raise ValueError("x and y need the same number of results")
    if a.size < minimum:
        raise ValueError(f"the comparison needs at least {minimum} samples")
    if not (np.isfinite(a).all() and np.isfinite(b).all()):
        raise ValueError("every result must be a number")
    return a, b


@dataclass(frozen=True)
class BlandAltman:
    """bias = mean of y - x; sd of the differences; loa = (lower, upper) limits of agreement;
    the *_ci95 are 95 % confidence intervals; mean and diff hold the plotted points."""

    n: int
    bias: float
    sd: float
    loa: tuple[float, float]
    bias_ci95: tuple[float, float]
    lower_ci95: tuple[float, float]
    upper_ci95: tuple[float, float]
    mean: np.ndarray
    diff: np.ndarray


def bland_altman(x: Sequence[float], y: Sequence[float], z: float = 1.96) -> BlandAltman:
    """Bland-Altman analysis of y (new method) against x (reference or old method)."""
    a, b = _pairs(x, y, 3)
    d = b - a
    n = d.size
    bias = float(d.mean())
    sd = float(d.std(ddof=1))
    t = float(stats.t.ppf(0.975, n - 1))
    se_bias = sd / math.sqrt(n)
    se_limit = sd * math.sqrt(3 / n)
    lower, upper = bias - z * sd, bias + z * sd
    return BlandAltman(
        n=n,
        bias=bias,
        sd=sd,
        loa=(lower, upper),
        bias_ci95=(bias - t * se_bias, bias + t * se_bias),
        lower_ci95=(lower - t * se_limit, lower + t * se_limit),
        upper_ci95=(upper - t * se_limit, upper + t * se_limit),
        mean=(a + b) / 2,
        diff=d,
    )


@dataclass(frozen=True)
class Line:
    """A comparison line y = intercept + slope * x with 95 % confidence intervals.

    method: "deming" or "passing-bablok". linear: Passing-Bablok cusum test passed (None for
    Deming). agrees: the slope interval holds 1 and the intercept interval holds 0.
    """

    method: str
    n: int
    slope: float
    intercept: float
    slope_ci95: tuple[float, float]
    intercept_ci95: tuple[float, float]
    linear: bool | None = None
    cusum: float | None = None
    cusum_critical: float | None = None

    @property
    def agrees(self) -> bool:
        lo_b, hi_b = self.slope_ci95
        lo_a, hi_a = self.intercept_ci95
        return lo_b <= 1 <= hi_b and lo_a <= 0 <= hi_a

    def predict(self, x: float | np.ndarray) -> float | np.ndarray:
        return self.intercept + self.slope * np.asarray(x, dtype=float)


def _deming_fit(a: np.ndarray, b: np.ndarray, ratio: float) -> tuple[float, float]:
    xm, ym = a.mean(), b.mean()
    sxx = float(np.sum((a - xm) ** 2))
    syy = float(np.sum((b - ym) ** 2))
    sxy = float(np.sum((a - xm) * (b - ym)))
    if sxy == 0:
        raise ValueError("x and y are uncorrelated: no line can be fitted")
    diff = syy - ratio * sxx
    slope = (diff + math.sqrt(diff**2 + 4 * ratio * sxy**2)) / (2 * sxy)
    return slope, float(ym - slope * xm)


def deming(x: Sequence[float], y: Sequence[float], error_ratio: float = 1.0) -> Line:
    """Deming regression of y on x; error_ratio = var(error in y) / var(error in x).

    slope = (Syy - r Sxx + sqrt((Syy - r Sxx)^2 + 4 r Sxy^2)) / (2 Sxy) with r the error
    ratio; intercept = mean(y) - slope * mean(x). 95 % intervals by the jackknife.
    """
    if not error_ratio > 0:
        raise ValueError("the error ratio must be greater than 0")
    a, b = _pairs(x, y, 3)
    slope, intercept = _deming_fit(a, b, error_ratio)
    n = a.size
    keep = ~np.eye(n, dtype=bool)
    leave = np.array([_deming_fit(a[k], b[k], error_ratio) for k in keep])
    t = float(stats.t.ppf(0.975, n - 2))
    intervals = []
    for full, parts in ((slope, leave[:, 0]), (intercept, leave[:, 1])):
        pseudo = n * full - (n - 1) * parts
        se = float(pseudo.std(ddof=1) / math.sqrt(n))
        intervals.append((full - t * se, full + t * se))
    return Line("deming", n, slope, intercept, intervals[0], intervals[1])


def passing_bablok(x: Sequence[float], y: Sequence[float]) -> Line:
    """Passing-Bablok regression with 95 % intervals and the cusum linearity test."""
    a, b = _pairs(x, y, 3)
    n = a.size
    i, j = np.triu_indices(n, k=1)
    dx, dy = a[j] - a[i], b[j] - b[i]
    valid = ~((dx == 0) & (dy == 0))  # identical pairs carry no slope
    dx, dy = dx[valid], dy[valid]
    with np.errstate(divide="ignore"):
        slopes = np.where(dx == 0, np.sign(dy) * np.inf, dy / np.where(dx == 0, 1, dx))
    slopes = np.sort(slopes[slopes != -1])
    big_n = slopes.size
    if big_n == 0:
        raise ValueError("no pair of samples gives a slope")
    k = int(np.sum(slopes < -1))

    def at(rank: int) -> float:  # 1-based rank, shifted by K
        return float(slopes[min(max(rank + k, 1), big_n) - 1])

    if big_n % 2:
        slope = at((big_n + 1) // 2)
    else:
        slope = 0.5 * (at(big_n // 2) + at(big_n // 2 + 1))
    c = 1.959964 * math.sqrt(n * (n - 1) * (2 * n + 5) / 18)
    m1 = int(round((big_n - c) / 2))
    m2 = big_n - m1 + 1
    slope_lo, slope_hi = at(m1), at(m2)
    intercept = float(np.median(b - slope * a))
    intercept_ci = (float(np.median(b - slope_hi * a)), float(np.median(b - slope_lo * a)))

    # cusum linearity test: residual signs ordered by their position along the line
    resid = b - intercept - slope * a
    above, below = int(np.sum(resid > 0)), int(np.sum(resid < 0))
    up = math.sqrt(below / above) if above else 0.0
    down = -math.sqrt(above / below) if below else 0.0
    score = np.where(resid > 0, up, np.where(resid < 0, down, 0.0))
    distance = (b + a / slope - intercept) / math.sqrt(1 + 1 / slope**2) if slope else a
    cusum = float(np.max(np.abs(np.cumsum(score[np.argsort(distance, kind="stable")]))))
    critical = 1.36 * math.sqrt(below + 1)
    return Line("passing-bablok", n, slope, intercept, (slope_lo, slope_hi), intercept_ci,
                linear=cusum <= critical, cusum=cusum, cusum_critical=critical)  # fmt: skip
