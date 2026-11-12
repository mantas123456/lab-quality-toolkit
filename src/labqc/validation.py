"""Method validation statistics: linearity, LOD/LOQ, precision and recovery.

LOD and LOQ use the calibration-curve approach of ICH Q2: 3.3 * s / slope and
10 * s / slope, where s is the residual standard deviation of the regression
(or the standard deviation of blanks, if supplied).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class Linearity:
    slope: float
    intercept: float
    r_squared: float
    residual_sd: float
    slope_ci95: tuple[float, float]
    intercept_ci95: tuple[float, float]
    residuals: np.ndarray
    n: int

    def predict_concentration(self, signal: float) -> float:
        return (signal - self.intercept) / self.slope


def linearity(concentration: Sequence[float], signal: Sequence[float]) -> Linearity:
    """Ordinary least-squares calibration line with 95% confidence intervals."""
    x = np.asarray(concentration, dtype=float)
    y = np.asarray(signal, dtype=float)
    if x.size != y.size or x.size < 3:
        raise ValueError("need at least three paired points")
    fit = stats.linregress(x, y)
    resid = y - (fit.intercept + fit.slope * x)
    dof = x.size - 2
    s = float(np.sqrt(np.sum(resid**2) / dof))
    t = stats.t.ppf(0.975, dof)
    return Linearity(
        slope=float(fit.slope),
        intercept=float(fit.intercept),
        r_squared=float(fit.rvalue**2),
        residual_sd=s,
        slope_ci95=(fit.slope - t * fit.stderr, fit.slope + t * fit.stderr),
        intercept_ci95=(
            fit.intercept - t * fit.intercept_stderr,
            fit.intercept + t * fit.intercept_stderr,
        ),
        residuals=resid,
        n=int(x.size),
    )


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
