"""Method validation statistics: linearity, LOD/LOQ, precision, recovery and trueness.

LOD and LOQ use the calibration-curve approach of ICH Q2: 3.3 * s / slope and
10 * s / slope, where s is the residual standard deviation of the regression
(or the standard deviation of blanks, if supplied).

Calibration lines can be weighted (1/x, 1/x^2 or explicit weights such as
1/s^2) when the signal spread grows with concentration. With replicate
standards, a lack-of-fit F-test checks whether a straight line is adequate.
Intermediate precision comes from one-way ANOVA of results grouped by day
(or analyst, instrument), and trueness from replicate results on a certified
reference material.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

Weights = str | Sequence[float] | None


@dataclass(frozen=True)
class LackOfFit:
    """Lack-of-fit F-test for a straight line, from replicate calibration standards.

    significant is True when p < 0.05: the line does not describe the data
    within the scatter of the replicates.
    """

    f: float
    p_value: float
    dof_lack_of_fit: int
    dof_pure_error: int

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05


@dataclass(frozen=True)
class Linearity:
    """A fitted calibration line.

    residuals are y - fitted; weighted_residuals are sqrt(w) * residuals,
    which should show no pattern against concentration if the weighting is
    right. lack_of_fit is None when there are no replicate standards.
    """

    slope: float
    intercept: float
    r_squared: float
    residual_sd: float
    slope_ci95: tuple[float, float]
    intercept_ci95: tuple[float, float]
    residuals: np.ndarray
    n: int
    weighting: str = "none"
    weighted_residuals: np.ndarray | None = None
    lack_of_fit: LackOfFit | None = None
    x: np.ndarray | None = field(default=None, repr=False)  # the standards' concentrations
    y: np.ndarray | None = field(default=None, repr=False)  # their signals

    def predict_concentration(self, signal: float) -> float:
        return (signal - self.intercept) / self.slope

    def predict_signal(self, concentration: float | np.ndarray) -> float | np.ndarray:
        """Signal on the fitted line: intercept + slope * concentration."""
        return self.intercept + self.slope * np.asarray(concentration, dtype=float)


def _weights(x: np.ndarray, weights: Weights) -> tuple[np.ndarray, str]:
    """Weights normalised to a mean of 1, and a label for them."""
    if weights is None or (isinstance(weights, str) and weights == "none"):
        return np.ones_like(x), "none"
    if isinstance(weights, str):
        if weights not in ("1/x", "1/x^2"):
            raise ValueError("weights must be None, '1/x', '1/x^2' or a sequence of weights")
        if np.any(x <= 0):
            raise ValueError(f"{weights} weighting needs all concentrations > 0")
        w = 1 / x if weights == "1/x" else 1 / x**2
        label = weights
    else:
        w = np.asarray(weights, dtype=float)
        if w.shape != x.shape or np.any(w <= 0):
            raise ValueError("explicit weights must be positive, one per point")
        label = "custom"
    return w * w.size / w.sum(), label


def _fit(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    xw, yw = np.average(x, weights=w), np.average(y, weights=w)
    slope = float(np.sum(w * (x - xw) * (y - yw)) / np.sum(w * (x - xw) ** 2))
    return slope, float(yw - slope * xw)


def lack_of_fit(
    concentration: Sequence[float], signal: Sequence[float], weights: Weights = None
) -> LackOfFit | None:
    """Lack-of-fit F-test; None when no concentration level has replicates.

    The residual sum of squares is split into pure error (scatter of
    replicates about their level mean, N - m dof) and lack of fit (the rest,
    m - 2 dof), where m is the number of distinct concentration levels:
    F = (SS_lof / (m - 2)) / (SS_pe / (N - m)).
    """
    x = np.asarray(concentration, dtype=float)
    y = np.asarray(signal, dtype=float)
    w, _ = _weights(x, weights)
    levels = np.unique(x)
    m, n = levels.size, x.size
    if n == m or m < 3:
        return None
    slope, intercept = _fit(x, y, w)
    ss_res = float(np.sum(w * (y - intercept - slope * x) ** 2))
    ss_pe = 0.0
    for level in levels:
        at = x == level
        ss_pe += float(np.sum(w[at] * (y[at] - np.average(y[at], weights=w[at])) ** 2))
    ss_lof = max(ss_res - ss_pe, 0.0)
    dof_lof, dof_pe = m - 2, n - m
    if ss_pe == 0:
        f, p = (math.inf, 0.0) if ss_lof > 0 else (0.0, 1.0)
    else:
        f = (ss_lof / dof_lof) / (ss_pe / dof_pe)
        p = float(stats.f.sf(f, dof_lof, dof_pe))
    return LackOfFit(float(f), p, dof_lof, dof_pe)


def linearity(
    concentration: Sequence[float], signal: Sequence[float], weights: Weights = None
) -> Linearity:
    """Least-squares calibration line with 95% confidence intervals.

    weights: None (ordinary least squares), "1/x", "1/x^2", or one positive
    weight per point (for example 1/s^2 from replicate standards). Weights
    are normalised to a mean of 1, so residual_sd is in signal units.
    """
    x = np.asarray(concentration, dtype=float)
    y = np.asarray(signal, dtype=float)
    if x.size != y.size or x.size < 3:
        raise ValueError("need at least three paired points")
    w, label = _weights(x, weights)
    slope, intercept = _fit(x, y, w)
    resid = y - (intercept + slope * x)
    dof = x.size - 2
    s = float(np.sqrt(np.sum(w * resid**2) / dof))
    xw, yw = np.average(x, weights=w), np.average(y, weights=w)
    sxx = float(np.sum(w * (x - xw) ** 2))
    se_slope = s / math.sqrt(sxx)
    se_intercept = s * math.sqrt(1 / w.sum() + xw**2 / sxx)
    t = stats.t.ppf(0.975, dof)
    ss_tot = float(np.sum(w * (y - yw) ** 2))
    return Linearity(
        slope=slope,
        intercept=intercept,
        r_squared=1 - float(np.sum(w * resid**2)) / ss_tot if ss_tot else 1.0,
        residual_sd=s,
        slope_ci95=(slope - t * se_slope, slope + t * se_slope),
        intercept_ci95=(intercept - t * se_intercept, intercept + t * se_intercept),
        residuals=resid,
        n=int(x.size),
        weighting=label,
        weighted_residuals=np.sqrt(w) * resid,
        lack_of_fit=lack_of_fit(x, y, weights),
        x=x,
        y=y,
    )


@dataclass(frozen=True)
class InversePrediction:
    """A concentration read back from a calibration line, with its standard uncertainty."""

    x0: float
    u_x0: float
    y0_mean: float
    m: int
    dof: int

    def interval(self, coverage: float = 0.95) -> tuple[float, float]:
        """x0 -/+ t(dof) * u_x0, the confidence interval of Miller & Miller."""
        t = float(stats.t.ppf(0.5 + coverage / 2, self.dof))
        return self.x0 - t * self.u_x0, self.x0 + t * self.u_x0


def inverse_prediction(cal: Linearity, y_readings: Sequence[float]) -> InversePrediction:
    """Concentration of a sample from m replicate signal readings, and its uncertainty.

    x0 = (y0 - a) / b with y0 the mean of the m readings, and the standard formula for
    an unweighted line (e.g. Miller & Miller, Statistics and Chemometrics for
    Analytical Chemistry, section 5.6):

        s_x0 = (s_y/x / b) * sqrt(1/m + 1/n + (y0 - y_mean)^2 / (b^2 * sum((x_i - x_mean)^2)))

    with n calibration points and n - 2 degrees of freedom. Only for unweighted lines.
    """
    if cal.x is None or cal.y is None:
        raise ValueError("this calibration has no stored standards; fit it with linearity()")
    if cal.weighting != "none":
        raise ValueError("inverse prediction here is for unweighted lines only")
    readings = np.asarray(y_readings, dtype=float)
    if readings.size < 1 or not np.isfinite(readings).all():
        raise ValueError("give at least one signal reading")
    if cal.slope == 0:
        raise ValueError("the calibration slope is 0")
    y0 = float(readings.mean())
    m = int(readings.size)
    x0 = (y0 - cal.intercept) / cal.slope
    sxx = float(np.sum((cal.x - cal.x.mean()) ** 2))
    term = (y0 - float(cal.y.mean())) ** 2 / (cal.slope**2 * sxx)
    u = cal.residual_sd / abs(cal.slope) * math.sqrt(1 / m + 1 / cal.n + term)
    return InversePrediction(x0, u, y0, m, cal.n - 2)


def lod_loq(cal: Linearity, blank_sd: float | None = None) -> tuple[float, float]:
    """Limits of detection and quantitation in concentration units."""
    s = cal.residual_sd if blank_sd is None else blank_sd
    return 3.3 * s / cal.slope, 10 * s / cal.slope


def precision(values: Sequence[float]) -> dict[str, float]:
    """Mean, standard deviation and relative standard deviation (%) of replicates."""
    x = np.asarray(values, dtype=float)
    mean, sd = float(x.mean()), float(x.std(ddof=1))
    return {"n": int(x.size), "mean": mean, "sd": sd, "rsd_percent": 100 * sd / mean}


def recovery(measured: float, unspiked: float, added: float) -> float:
    """Spike recovery in percent."""
    return 100 * (measured - unspiked) / added


@dataclass(frozen=True)
class IntermediatePrecision:
    """One-way ANOVA of results grouped by day (or analyst, instrument).

    sd_repeatability = sqrt(MS_within); sd_between = sqrt((MS_between -
    MS_within) / n0), set to 0 when negative; sd_intermediate =
    sqrt(sd_repeatability^2 + sd_between^2). n0 is the replicates per group
    (ISO 5725-2 formula for unequal group sizes).
    """

    n_groups: int
    n_total: int
    mean: float
    ms_between: float
    ms_within: float
    f: float
    p_value: float
    sd_repeatability: float
    sd_between: float
    sd_intermediate: float

    @property
    def rsd_repeatability_percent(self) -> float:
        return 100 * self.sd_repeatability / self.mean

    @property
    def rsd_intermediate_percent(self) -> float:
        return 100 * self.sd_intermediate / self.mean


def intermediate_precision(
    df: pd.DataFrame, value_col: str = "value", group_col: str = "day"
) -> IntermediatePrecision:
    """Repeatability, between-group and intermediate precision SDs by one-way ANOVA."""
    data = df[[group_col, value_col]].dropna()
    groups = [g[value_col].to_numpy(dtype=float) for _, g in data.groupby(group_col, sort=False)]
    p = len(groups)
    sizes = np.array([g.size for g in groups])
    n = int(sizes.sum())
    if p < 2 or n <= p:
        raise ValueError("need at least two groups and at least one group with replicates")
    grand = float(data[value_col].mean())
    ss_between = float(sum(g.size * (g.mean() - grand) ** 2 for g in groups))
    ss_within = float(sum(np.sum((g - g.mean()) ** 2) for g in groups))
    ms_between = ss_between / (p - 1)
    ms_within = ss_within / (n - p)
    n0 = (n - np.sum(sizes**2) / n) / (p - 1)
    if ms_within == 0:
        f, p_value = (math.inf, 0.0) if ms_between > 0 else (0.0, 1.0)
    else:
        f = ms_between / ms_within
        p_value = float(stats.f.sf(f, p - 1, n - p))
    s_r = math.sqrt(ms_within)
    s_between = math.sqrt(max(ms_between - ms_within, 0.0) / n0)
    return IntermediatePrecision(
        n_groups=p,
        n_total=n,
        mean=grand,
        ms_between=ms_between,
        ms_within=ms_within,
        f=float(f),
        p_value=p_value,
        sd_repeatability=s_r,
        sd_between=s_between,
        sd_intermediate=math.hypot(s_r, s_between),
    )


@dataclass(frozen=True)
class Trueness:
    """Bias against a certified reference material (CRM).

    t and p_value: one-sample t-test of the mean against the certified value
    (n - 1 dof), ignoring the CRM uncertainty. passed: the ERM Application
    Note 1 criterion |bias| <= U_bias, with U_bias = 2 * sqrt(s^2 / n + u_crm^2),
    which does include the CRM uncertainty.
    """

    n: int
    mean: float
    sd: float
    bias: float
    bias_percent: float
    recovery_percent: float
    t: float
    p_value: float
    u_bias: float
    U_bias: float
    passed: bool


def trueness(results: Sequence[float], crm_value: float, crm_u: float = 0.0) -> Trueness:
    """Trueness from replicate results on a CRM.

    crm_u is the standard uncertainty of the certified value (a certificate's
    expanded uncertainty divided by its k).
    """
    x = np.asarray(results, dtype=float)
    if x.size < 2:
        raise ValueError("need at least two results")
    if crm_u < 0:
        raise ValueError("crm_u must not be negative")
    mean, sd = float(x.mean()), float(x.std(ddof=1))
    bias = mean - crm_value
    sem = sd / math.sqrt(x.size)
    if sem == 0:
        t, p_value = (math.inf, 0.0) if bias else (0.0, 1.0)
    else:
        t = bias / sem
        p_value = float(2 * stats.t.sf(abs(t), x.size - 1))
    u_bias = math.hypot(sem, crm_u)
    return Trueness(
        n=int(x.size),
        mean=mean,
        sd=sd,
        bias=bias,
        bias_percent=100 * bias / crm_value,
        recovery_percent=100 * mean / crm_value,
        t=float(t),
        p_value=p_value,
        u_bias=u_bias,
        U_bias=2 * u_bias,
        passed=abs(bias) <= 2 * u_bias,
    )
