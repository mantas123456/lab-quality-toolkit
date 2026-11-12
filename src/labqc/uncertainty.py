"""Measurement uncertainty budgets following the GUM (JCGM 100:2008).

A budget is a list of input components. Each has a standard uncertainty u_i,
a sensitivity coefficient c_i and degrees of freedom v_i (infinite for most
Type B estimates). The combined standard uncertainty is

    u_c = sqrt(sum((c_i * u_i)^2))

for uncorrelated inputs. The effective degrees of freedom come from the
Welch-Satterthwaite formula, and the coverage factor k from Student's t.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

# Divisors that turn a half-width a into a standard uncertainty (GUM 4.3.7, 4.3.9).
DIVISORS = {
    "normal": 1.0,  # value already a standard uncertainty
    "rectangular": math.sqrt(3),
    "triangular": math.sqrt(6),
    "u-shaped": math.sqrt(2),
}


@dataclass(frozen=True)
class Component:
    """One input to the budget.

    value: the quoted uncertainty. For "normal" this is a standard
        uncertainty, or an expanded one if `k` is given. For the other
        distributions it is the half-width of the interval.
    """

    name: str
    value: float
    distribution: str = "normal"
    k: float = 1.0
    sensitivity: float = 1.0
    dof: float = math.inf
    unit: str = ""

    @property
    def standard_uncertainty(self) -> float:
        if self.distribution not in DIVISORS:
            raise ValueError(f"unknown distribution {self.distribution!r}")
        divisor = self.k if self.distribution == "normal" else DIVISORS[self.distribution]
        return abs(self.value) / divisor

    @property
    def contribution(self) -> float:
        """|c_i| * u_i, in units of the result."""
        return abs(self.sensitivity) * self.standard_uncertainty


def type_a(readings: Sequence[float], name: str = "Repeatability") -> Component:
    """Type A component from repeated readings: standard deviation of the mean."""
    x = np.asarray(readings, dtype=float)
    if x.size < 2:
        raise ValueError("need at least two readings")
    sem = x.std(ddof=1) / math.sqrt(x.size)
    return Component(name, sem, "normal", dof=x.size - 1)


@dataclass(frozen=True)
class Result:
    combined: float
    effective_dof: float
    k: float
    expanded: float
    coverage: float
    table: pd.DataFrame

    def __str__(self) -> str:
        dof = "inf" if math.isinf(self.effective_dof) else f"{self.effective_dof:.1f}"
        return (
            f"u_c = {self.combined:.4g}, v_eff = {dof}, k = {self.k:.2f}, "
            f"U ({self.coverage:.0%}) = {self.expanded:.4g}"
        )


def welch_satterthwaite(components: Sequence[Component]) -> float:
    uc4 = sum(c.contribution**2 for c in components) ** 2
    denom = sum(c.contribution**4 / c.dof for c in components if not math.isinf(c.dof))
    return math.inf if denom == 0 else uc4 / denom


def coverage_factor(dof: float, coverage: float = 0.95) -> float:
    if math.isinf(dof):
        return float(stats.norm.ppf(0.5 + coverage / 2))
    return float(stats.t.ppf(0.5 + coverage / 2, dof))


def combine(
    components: Sequence[Component], coverage: float = 0.95, k: float | None = None
) -> Result:
    """Combine uncorrelated components.

    Pass `k` to fix the coverage factor (k = 2 is common in calibration
    certificates). Otherwise k comes from the effective degrees of freedom.
    """
    if not components:
        raise ValueError("budget is empty")
    uc = math.sqrt(sum(c.contribution**2 for c in components))
    dof = welch_satterthwaite(components)
    k_used = k if k is not None else coverage_factor(dof, coverage)
    table = pd.DataFrame(
        [
            {
                "component": c.name,
                "distribution": c.distribution,
                "u_i": c.standard_uncertainty,
                "c_i": c.sensitivity,
                "contribution": c.contribution,
                "dof": c.dof,
                "share_of_variance": c.contribution**2 / uc**2 if uc else 0.0,
            }
            for c in components
        ]
    ).sort_values("share_of_variance", ascending=False)
    return Result(uc, dof, k_used, k_used * uc, coverage, table.reset_index(drop=True))


def propagate(
    func: Callable[..., float],
    values: Mapping[str, float],
    inputs: Mapping[str, Component],
    extra: Sequence[Component] = (),
    coverage: float = 0.95,
    k: float | None = None,
) -> tuple[float, Result]:
    """Propagate input uncertainties through a measurement model y = func(**values).

    Sensitivity coefficients are partial derivatives found by central
    differences, so the model can be any Python function. `inputs` maps an
    argument name to its uncertainty component (the component's own
    sensitivity is replaced). `extra` adds components already expressed in
    units of the result, such as the repeatability of y.
    """
    y = float(func(**values))
    comps = []
    for name, comp in inputs.items():
        x = values[name]
        h = 1e-6 * max(abs(x), 1.0)
        up = func(**{**values, name: x + h})
        down = func(**{**values, name: x - h})
        c = (up - down) / (2 * h)
        comps.append(
            Component(comp.name, comp.value, comp.distribution, comp.k, c, comp.dof, comp.unit)
        )
    return y, combine([*comps, *extra], coverage=coverage, k=k)
