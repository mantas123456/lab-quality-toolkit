"""Equipment drift from successive calibration certificates, and the calibration interval.

Each certificate gives the instrument's error at a check point (reading minus reference
value) and its expanded uncertainty U. A straight line fitted to error against time gives
the drift per year. Projected forward, the line says when the error, widened by U, is
expected to reach the tolerance (the maximum permissible error the laboratory allows).

Interval rule used here (labqc's own, in the spirit of the "calibration history" methods of
ILAC-G24 / OIML D 10; state it in your procedure if you use it):

    t_reach = time from the last calibration until |predicted error| + U reaches the
              tolerance (U of the last certificate);
    interval = the current interval (default: the median time between certificates).

    shorten     t_reach < interval: the error may leave the tolerance before the next
                calibration; suggested interval = t_reach, rounded down to whole months.
    lengthen    t_reach >= 2 x interval and every certificate had |error| + U within half
                the tolerance: the history supports a longer interval; suggested
                1.5 x interval at most.
    keep        otherwise.

A drift line from two or three certificates is weak evidence; treat the suggestion as an
input to the decision, together with use, checks between calibrations and the risk of a
wrong result.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

DAYS_PER_YEAR = 365.25


def _to_dates(dates: Sequence) -> list[date]:
    try:
        out = [pd.Timestamp(d).date() for d in dates]
    except (ValueError, TypeError) as err:
        raise ValueError(f"a date could not be read: {err}") from None
    if any(b <= a for a, b in zip(out, out[1:], strict=False)):
        raise ValueError("the certificate dates must be in order, oldest first, all different")
    return out


@dataclass(frozen=True)
class Drift:
    """Outcome of `drift`.

    drift_per_year: slope of error against time. intercept: fitted error at the first date.
    predicted_now: fitted error at the last date. reach_date: date when |predicted error| + U
    reaches the tolerance (None if the line never gets there, e.g. no drift). t_reach_years:
    from the last calibration to reach_date. interval_years: the current interval.
    suggestion: "shorten", "keep" or "lengthen"; suggested_interval_years and reason.
    table: the certificates with the fitted error and |error| + U.
    """

    n: int
    drift_per_year: float
    intercept: float
    predicted_now: float
    tolerance: float
    reach_date: date | None
    t_reach_years: float | None
    interval_years: float
    suggestion: str
    suggested_interval_years: float
    reason: str
    table: pd.DataFrame


def drift(
    dates: Sequence,
    errors: Sequence[float],
    U: float | Sequence[float],
    tolerance: float,
    interval_years: float | None = None,
) -> Drift:
    """Fit error against time from successive certificates and suggest a calibration interval.

    dates: certificate dates, oldest first. errors: the error at the same check point on each
    certificate. U: the expanded uncertainty, one value or one per certificate. tolerance: the
    maximum permissible error (positive). interval_years: the current interval; default the
    median time between the certificates. See the module docstring for the rule.
    """
    when = _to_dates(dates)
    e = np.asarray(errors, dtype=float)
    if e.ndim != 1 or e.size != len(when):
        raise ValueError("give one error per certificate date")
    if e.size < 2:
        raise ValueError("a drift needs at least two certificates")
    u = np.broadcast_to(np.asarray(U, dtype=float), e.shape).astype(float)
    if (u < 0).any() or not np.isfinite(np.concatenate([e, u])).all():
        raise ValueError("errors and U must be numbers, U not negative")
    if not tolerance > 0:
        raise ValueError("the tolerance must be greater than 0")

    t = np.array([(d - when[0]).days / DAYS_PER_YEAR for d in when])
    slope, intercept = (float(v) for v in np.polyfit(t, e, 1))
    predicted_now = intercept + slope * t[-1]
    interval = float(np.median(np.diff(t))) if interval_years is None else float(interval_years)
    if not interval > 0:
        raise ValueError("the interval must be greater than 0")

    u_last = float(u[-1])
    reach_years: float | None
    if abs(predicted_now) + u_last >= tolerance:
        reach_years = 0.0  # already there
    elif slope == 0:
        reach_years = None  # no drift: never
    else:
        # inside the tolerance now and moving towards the edge on the side of the drift:
        # intercept + slope * T = sign(slope) * (tolerance - U) has its root after today
        edge = math.copysign(tolerance - u_last, slope)
        reach_years = (edge - intercept) / slope - float(t[-1])
    reach_date = (
        None if reach_years is None else when[-1] + timedelta(days=reach_years * DAYS_PER_YEAR)
    )

    margin_ok = bool(np.all(np.abs(e) + u <= tolerance / 2))
    if reach_years is not None and reach_years < interval:
        suggestion = "shorten"
        suggested = math.floor(reach_years * 12) / 12
        reason = (
            f"|error| + U is predicted to reach the tolerance {reach_years:.2f} years after the "
            f"last calibration, before the current interval of {interval:.2f} years ends."
        )
    elif (reach_years is None or reach_years >= 2 * interval) and margin_ok:
        suggestion = "lengthen"
        suggested = 1.5 * interval
        reach = "is not predicted" if reach_years is None else f"is {reach_years:.1f} years away"
        reason = (
            f"Reaching the tolerance {reach}, at least twice the interval, and every "
            "certificate had |error| + U within half the tolerance."
        )
    else:
        suggestion = "keep"
        suggested = interval
        reason = "The predicted error stays within the tolerance over the next interval."

    table = pd.DataFrame(
        {
            "date": when,
            "error": e,
            "U": u,
            "fitted": intercept + slope * t,
            "abs_error_plus_U": np.abs(e) + u,
        }
    )
    return Drift(
        n=int(e.size),
        drift_per_year=slope,
        intercept=intercept,
        predicted_now=predicted_now,
        tolerance=float(tolerance),
        reach_date=reach_date,
        t_reach_years=reach_years,
        interval_years=interval,
        suggestion=suggestion,
        suggested_interval_years=suggested,
        reason=reason,
        table=table,
    )
