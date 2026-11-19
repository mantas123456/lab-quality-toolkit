"""Top-down measurement uncertainty from QC and PT or CRM data (Nordtest TR 537 approach).

Instead of a full GUM budget, the uncertainty of a routine method is built from two terms the
laboratory already measures:

u(Rw)    within-laboratory reproducibility: the standard deviation of a control sample run
         over a long period (different days, analysts, calibrations), optionally combined
         with the repeatability from duplicate analyses of real samples when the control
         sample does not go through the whole procedure:
             u(Rw) = sqrt(s_control^2 + s_r^2)
u(bias)  method and laboratory bias, from proficiency-testing rounds or a certified
         reference material (CRM):
             PT:  u(bias) = sqrt(RMS_bias^2 + u(Cref)^2),
                  RMS_bias = sqrt(sum(b_i^2) / n), u(Cref) = mean of the u of the assigned values
             CRM: u(bias) = sqrt(b^2 + (s_bias / sqrt(n))^2 + u(Cref)^2),
                  b = mean of the n results - certified value

u_c = sqrt(u(Rw)^2 + u(bias)^2) and U = k * u_c with k = 2 (about 95 %).

Work either in the units of the result or relative, in percent (`relative=True`), which suits
methods used over a wide concentration range. Do not mix the two: every term must be in the
same form before combining.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd


def _array(values: Sequence[float], what: str, minimum: int) -> np.ndarray:
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or x.size < minimum:
        raise ValueError(f"{what} needs at least {minimum} values")
    if not np.isfinite(x).all():
        raise ValueError(f"{what} must all be numbers")
    return x


def u_rw(qc_values: Sequence[float], s_r: float | None = None, relative: bool = False) -> float:
    """Within-laboratory reproducibility u(Rw) from a control sample series.

    The sample standard deviation of the control results (n - 1), as a percentage of their
    mean with `relative=True`. Pass `s_r` (for example from `s_r_duplicates`, in the same
    form) to add repeatability on real samples: u(Rw) = sqrt(s_control^2 + s_r^2).
    """
    x = _array(qc_values, "the control series", 2)
    s = float(x.std(ddof=1))
    if relative:
        mean = float(x.mean())
        if mean == 0:
            raise ValueError("a relative u(Rw) needs a control mean other than 0")
        s = 100 * s / abs(mean)
    if s_r is not None:
        if s_r < 0:
            raise ValueError("s_r must not be negative")
        s = math.hypot(s, s_r)
    return s


def s_r_duplicates(
    first: Sequence[float], second: Sequence[float], relative: bool = False, method: str = "sd"
) -> float:
    """Repeatability standard deviation from duplicate analyses of n samples.

    method="sd":    s_r = sqrt(sum(d_i^2) / (2 n)), d_i = difference of a pair.
    method="range": s_r = mean |d_i| / 1.128 (d2 for pairs), as on a range control chart.
    With `relative=True` each difference is first taken as a percentage of its pair's mean,
    which suits samples of different concentrations.
    """
    a = _array(first, "the duplicates", 2)
    b = _array(second, "the duplicates", 2)
    if a.size != b.size:
        raise ValueError("both duplicate series need the same number of results")
    d = a - b
    if relative:
        means = (a + b) / 2
        if (means == 0).any():
            raise ValueError("a relative difference needs a pair mean other than 0")
        d = 100 * d / np.abs(means)
    if method == "sd":
        return float(math.sqrt(np.sum(d**2) / (2 * d.size)))
    if method == "range":
        return float(np.mean(np.abs(d)) / 1.128)
    raise ValueError("method must be 'sd' or 'range'")


@dataclass(frozen=True)
class Bias:
    """Bias component from PT rounds or a CRM.

    source: "PT" or "CRM". n: rounds (PT) or results (CRM). bias: RMS of the PT biases, or
    the mean bias against the CRM. s_bias: standard deviation of the CRM results (None for
    PT). u_ref: u(Cref). u_bias: the combined bias uncertainty. table: one row per PT round
    or CRM result.
    """

    source: str
    n: int
    bias: float
    s_bias: float | None
    u_ref: float
    u_bias: float
    relative: bool
    table: pd.DataFrame


def u_bias_pt(
    results: Sequence[float],
    assigned: Sequence[float],
    u_assigned: Sequence[float],
    relative: bool = False,
) -> Bias:
    """u(bias) from n proficiency-testing rounds (Nordtest TR 537).

    b_i = x_i - X_i (or 100 (x_i - X_i) / X_i with `relative=True`), RMS_bias =
    sqrt(sum(b_i^2) / n), u(Cref) = mean of the standard uncertainties of the assigned
    values (relative to X_i when relative), u(bias) = sqrt(RMS_bias^2 + u(Cref)^2).
    Nordtest suggests at least six rounds.
    """
    x = _array(results, "the PT results", 1)
    ref = _array(assigned, "the assigned values", 1)
    u_ref = _array(u_assigned, "the assigned-value uncertainties", 1)
    if not x.size == ref.size == u_ref.size:
        raise ValueError("results, assigned values and their uncertainties need equal length")
    if (u_ref < 0).any():
        raise ValueError("the uncertainties of the assigned values must not be negative")
    b = x - ref
    u_i = u_ref
    if relative:
        if (ref == 0).any():
            raise ValueError("a relative bias needs assigned values other than 0")
        b = 100 * b / np.abs(ref)
        u_i = 100 * u_ref / np.abs(ref)
    rms = float(math.sqrt(np.mean(b**2)))
    u_cref = float(np.mean(u_i))
    table = pd.DataFrame(
        {"result": x, "assigned": ref, "u_assigned": u_ref, "bias": b, "u_ref": u_i}
    )
    return Bias("PT", int(x.size), rms, None, u_cref, math.hypot(rms, u_cref), relative, table)


def u_bias_crm(
    results: Sequence[float], certified: float, u_certified: float, relative: bool = False
) -> Bias:
    """u(bias) from n results on one certified reference material (Nordtest TR 537).

    b = mean - certified, s_bias = SD of the results, u(bias) = sqrt(b^2 + (s_bias /
    sqrt(n))^2 + u(Cref)^2), with u(Cref) the standard uncertainty of the certified value.
    With `relative=True` b, s_bias and u(Cref) are percentages of the certified value.
    """
    x = _array(results, "the CRM results", 2)
    if u_certified < 0:
        raise ValueError("the uncertainty of the certified value must not be negative")
    b = float(x.mean() - certified)
    s = float(x.std(ddof=1))
    u_ref = float(u_certified)
    bias_i = x - certified
    if relative:
        if certified == 0:
            raise ValueError("a relative bias needs a certified value other than 0")
        scale = 100 / abs(certified)
        b, s, u_ref, bias_i = b * scale, s * scale, u_ref * scale, bias_i * scale
    u = math.sqrt(b**2 + s**2 / x.size + u_ref**2)
    table = pd.DataFrame({"result": x, "bias": bias_i})
    return Bias("CRM", int(x.size), b, s, u_ref, u, relative, table)


@dataclass(frozen=True)
class TopDownResult:
    """u(Rw), u(bias), u_c = sqrt(u(Rw)^2 + u(bias)^2), k and U = k * u_c.

    table: one row per term (u(Rw), and the parts of u(bias)) with its share of u_c^2.
    relative: True if every term is a percentage.
    """

    u_rw: float
    u_bias: float
    combined: float
    k: float
    expanded: float
    relative: bool
    table: pd.DataFrame

    def summary(self) -> str:
        pct = " %" if self.relative else ""
        return (
            f"u(Rw) = {self.u_rw:.3g}{pct}, u(bias) = {self.u_bias:.3g}{pct}, "
            f"u_c = {self.combined:.3g}{pct}, U (k = {self.k:g}) = {self.expanded:.3g}{pct}"
        )

    def __str__(self) -> str:
        return self.summary()


def combine_topdown(
    u_rw_value: float, bias: Bias | float, k: float = 2.0, relative: bool = False
) -> TopDownResult:
    """Combine u(Rw) and u(bias) into u_c and U = k * u_c (Nordtest TR 537 uses k = 2).

    `bias` is a `Bias` from `u_bias_pt` / `u_bias_crm`, or a u(bias) value already in the
    same form as u(Rw); then `relative` says whether both are percentages.
    """
    if u_rw_value < 0:
        raise ValueError("u(Rw) must not be negative")
    if not k > 0:
        raise ValueError("k must be greater than 0")
    if isinstance(bias, Bias):
        ub = bias.u_bias
        parts = [(f"bias ({bias.source}, {'RMS' if bias.source == 'PT' else 'mean'})", bias.bias)]
        if bias.s_bias is not None:
            parts.append(("bias scatter, s_bias / sqrt(n)", bias.s_bias / math.sqrt(bias.n)))
        parts.append(("reference value, u(Cref)", bias.u_ref))
        relative = bias.relative
    else:
        ub = float(bias)
        if ub < 0:
            raise ValueError("u(bias) must not be negative")
        parts = [("u(bias)", ub)]
    uc = math.hypot(u_rw_value, ub)
    rows = [("within-lab reproducibility, u(Rw)", u_rw_value), *parts]
    table = pd.DataFrame(rows, columns=["term", "u"])
    table["share_of_variance"] = table["u"] ** 2 / uc**2 if uc else 0.0
    return TopDownResult(u_rw_value, ub, uc, k, k * uc, relative, table)
