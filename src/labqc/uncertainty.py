"""Measurement uncertainty budgets following the GUM (JCGM 100:2008) and its Supplement 1.

A budget is a list of input components. Each has a standard uncertainty u_i,
a sensitivity coefficient c_i and degrees of freedom v_i (infinite for most
Type B estimates). The combined standard uncertainty is

    u_c^2 = sum((c_i * u_i)^2) + sum_{i != j} c_i * c_j * u_i * u_j * r_ij

where r_ij is the correlation coefficient between inputs i and j (GUM 5.2.2);
the second sum is zero for uncorrelated inputs. The effective degrees of
freedom come from the Welch-Satterthwaite formula, and the coverage factor k
from Student's t.

For non-linear models, `monte_carlo` propagates the input distributions
themselves (JCGM 101:2008, GUM Supplement 1) instead of their first-order
sensitivities.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

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

Correlation = Mapping[tuple[str, str], float]
"""Correlation coefficients r_ij keyed by a pair of component names, e.g. {("m1", "m2"): 0.9}.
One order of each pair is enough; pairs not listed are uncorrelated."""


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
            raise ValueError(
                "Distribution must be normal, rectangular, triangular or u-shaped, "
                f"not {self.distribution!r}"
            )
        divisor = self.k if self.distribution == "normal" else DIVISORS[self.distribution]
        return abs(self.value) / divisor

    @property
    def contribution(self) -> float:
        """|c_i| * u_i, in units of the result."""
        return abs(self.sensitivity) * self.standard_uncertainty


TABLE_COLUMNS = ("name", "value", "distribution", "k", "sensitivity", "dof", "unit")


def _blank(raw: object) -> bool:
    return raw is None or raw == "" or (isinstance(raw, float) and math.isnan(raw))


def components_from_table(table: pd.DataFrame) -> list[Component]:
    """Build components from a table, e.g. an uploaded CSV or an edited grid.

    Columns: name and value are required; distribution (default "normal"),
    k (1), sensitivity (1), dof (blank or "inf" = infinite) and unit ("")
    are optional. Fully empty rows are skipped. Raises ValueError with the
    row number (counting from 1) and a plain explanation for bad input.
    """
    missing = [c for c in ("name", "value") if c not in table.columns]
    if missing:
        raise ValueError(f"The table needs the column(s): {', '.join(missing)}")
    rows = table.dropna(how="all")
    if rows.empty:
        raise ValueError("The budget is empty: add at least one component")

    def number(row: int, column: str, raw: object, default: float) -> float:
        if _blank(raw):
            return default
        try:
            return float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"Row {row}: {column} must be a number, not {raw!r}") from None

    components = []
    for row, (_, r) in enumerate(rows.iterrows(), start=1):
        name = r.get("name")
        if _blank(name) or not str(name).strip():
            raise ValueError(f"Row {row}: every component needs a name")
        value = number(row, "value", r.get("value"), math.nan)
        if math.isnan(value):
            raise ValueError(f"Row {row}: value is missing")
        dist = r.get("distribution")
        dist = "normal" if _blank(dist) else str(dist).strip().lower()
        if dist not in DIVISORS:
            raise ValueError(
                f"Row {row}: Distribution must be normal, rectangular, triangular or u-shaped, "
                f"not {dist!r}"
            )
        k = number(row, "k", r.get("k"), 1.0)
        dof = number(row, "dof", r.get("dof"), math.inf)
        if k <= 0:
            raise ValueError(f"Row {row}: k must be greater than 0")
        if dof <= 0:
            raise ValueError(f"Row {row}: dof must be greater than 0 (blank means infinite)")
        unit = r.get("unit")
        components.append(
            Component(
                str(name).strip(),
                value,
                dist,
                k,
                number(row, "sensitivity", r.get("sensitivity"), 1.0),
                dof,
                "" if _blank(unit) else str(unit),
            )
        )
    return components


def type_a(readings: Sequence[float], name: str = "Repeatability") -> Component:
    """Type A component from repeated readings: standard deviation of the mean."""
    x = np.asarray(readings, dtype=float)
    if x.size < 2:
        raise ValueError("need at least two readings")
    sem = x.std(ddof=1) / math.sqrt(x.size)
    return Component(name, sem, "normal", dof=x.size - 1)


@dataclass(frozen=True)
class Result:
    """Outcome of `combine` or `propagate`.

    combined: u_c. expanded: U = k * u_c. covariance: the part of u_c^2 that
    comes from correlations (zero for uncorrelated inputs). value: the
    measurement result y, when known; it enables the relative uncertainties.
    """

    combined: float
    effective_dof: float
    k: float
    expanded: float
    coverage: float
    table: pd.DataFrame
    value: float | None = None
    covariance: float = 0.0

    @property
    def relative_combined(self) -> float:
        """u_c / |y|."""
        return self.combined / self._abs_value()

    @property
    def relative_expanded(self) -> float:
        """U / |y|."""
        return self.expanded / self._abs_value()

    def _abs_value(self) -> float:
        if self.value is None:
            raise ValueError("relative uncertainty needs the result value; pass value= to combine")
        if self.value == 0:
            raise ValueError("relative uncertainty is undefined for a result of zero")
        return abs(self.value)

    def summary(self, relative: bool = False) -> str:
        """One-line summary; with `relative=True` also u_c/|y| and U/|y| in percent."""
        dof = "inf" if math.isinf(self.effective_dof) else f"{self.effective_dof:.1f}"
        text = (
            f"u_c = {self.combined:.4g}, v_eff = {dof}, k = {self.k:.2f}, "
            f"U ({self.coverage:.0%}) = {self.expanded:.4g}"
        )
        if relative:
            text += (
                f" | u_c/|y| = {self.relative_combined:.3%}, U/|y| = {self.relative_expanded:.3%}"
            )
        return text

    def __str__(self) -> str:
        return self.summary()


def welch_satterthwaite(components: Sequence[Component]) -> float:
    """Effective degrees of freedom (GUM G.4.1), for independent inputs."""
    uc4 = sum(c.contribution**2 for c in components) ** 2
    denom = sum(c.contribution**4 / c.dof for c in components if not math.isinf(c.dof))
    return math.inf if denom == 0 else uc4 / denom


def coverage_factor(dof: float, coverage: float = 0.95) -> float:
    if math.isinf(dof):
        return float(stats.norm.ppf(0.5 + coverage / 2))
    return float(stats.t.ppf(0.5 + coverage / 2, dof))


def correlation_matrix(names: Sequence[str], correlation: Correlation | None) -> np.ndarray:
    """Build and check the correlation matrix R for components in `names` order.

    Raises ValueError if a coefficient is outside [-1, 1], a name is unknown,
    a pair is given twice with different values, a component's correlation
    with itself is not 1, or R is not positive semi-definite.
    """
    n = len(names)
    matrix = np.eye(n)
    if not correlation:
        return matrix
    if len(set(names)) != n:
        raise ValueError("component names must be unique when correlations are given")
    index = {name: i for i, name in enumerate(names)}
    seen: dict[tuple[int, int], float] = {}
    for (a, b), r in correlation.items():
        if a not in index or b not in index:
            raise ValueError(f"correlation names an unknown component: ({a!r}, {b!r})")
        r = float(r)
        if not -1.0 <= r <= 1.0:
            raise ValueError(f"correlation ({a!r}, {b!r}) = {r} is outside [-1, 1]")
        i, j = index[a], index[b]
        if i == j:
            if r != 1.0:
                raise ValueError(f"correlation of {a!r} with itself must be 1")
            continue
        key = (min(i, j), max(i, j))
        if key in seen and not math.isclose(seen[key], r):
            raise ValueError(f"correlation ({a!r}, {b!r}) given twice with different values")
        seen[key] = r
        matrix[i, j] = matrix[j, i] = r
    if np.linalg.eigvalsh(matrix).min() < -1e-10:
        raise ValueError("correlation matrix is not positive semi-definite")
    return matrix


def combine(
    components: Sequence[Component],
    coverage: float = 0.95,
    k: float | None = None,
    correlation: Correlation | None = None,
    value: float | None = None,
) -> Result:
    """Combine components into u_c, k and U.

    Pass `k` to fix the coverage factor (k = 2 is common in calibration
    certificates). Otherwise k comes from the effective degrees of freedom.

    `correlation` maps pairs of component names to r_ij and adds the
    covariance terms 2 * c_i * c_j * u_i * u_j * r_ij to u_c^2; the sign of
    each sensitivity coefficient matters here. With correlations, the
    share_of_variance column no longer sums to 1: the rest is in
    `Result.covariance`. Welch-Satterthwaite is used as for independent inputs.

    `value` is the measurement result y, needed only for relative uncertainties.
    """
    if not components:
        raise ValueError("budget is empty")
    matrix = correlation_matrix([c.name for c in components], correlation)
    signed = np.array([c.sensitivity * c.standard_uncertainty for c in components])
    variance_sum = float(signed @ signed)
    uc2 = max(float(signed @ matrix @ signed), 0.0)
    uc = math.sqrt(uc2)
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
                "share_of_variance": c.contribution**2 / uc2 if uc2 else 0.0,
            }
            for c in components
        ]
    ).sort_values("share_of_variance", ascending=False)
    return Result(
        uc,
        dof,
        k_used,
        k_used * uc,
        coverage,
        table.reset_index(drop=True),
        value=value,
        covariance=uc2 - variance_sum,
    )


def _rename_correlation(
    correlation: Correlation | None, inputs: Mapping[str, Component]
) -> Correlation | None:
    """Let correlation keys use either an input's argument name or its component name."""
    if not correlation:
        return correlation
    names = {arg: comp.name for arg, comp in inputs.items()}
    return {(names.get(a, a), names.get(b, b)): r for (a, b), r in correlation.items()}


def propagate(
    func: Callable[..., float],
    values: Mapping[str, float],
    inputs: Mapping[str, Component],
    extra: Sequence[Component] = (),
    coverage: float = 0.95,
    k: float | None = None,
    correlation: Correlation | None = None,
) -> tuple[float, Result]:
    """Propagate input uncertainties through a measurement model y = func(**values).

    Sensitivity coefficients are partial derivatives found by central
    differences, so the model can be any Python function. `inputs` maps an
    argument name to its uncertainty component (the component's own
    sensitivity is replaced). `extra` adds components already expressed in
    units of the result, such as the repeatability of y. `correlation` keys
    may use argument names or component names.
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
    result = combine(
        [*comps, *extra],
        coverage=coverage,
        k=k,
        correlation=_rename_correlation(correlation, inputs),
        value=y,
    )
    return y, result


@dataclass(frozen=True, eq=False)
class MonteCarloResult:
    """Outcome of `monte_carlo` (JCGM 101:2008).

    mean and standard_uncertainty are the estimate of y and u(y); [low, high]
    is the shortest interval holding `coverage` of the samples (JCGM 101 7.7.2).
    """

    mean: float
    standard_uncertainty: float
    low: float
    high: float
    coverage: float
    samples: np.ndarray = field(repr=False)

    @property
    def interval(self) -> tuple[float, float]:
        return self.low, self.high

    def __str__(self) -> str:
        return (
            f"y = {self.mean:.4g}, u(y) = {self.standard_uncertainty:.4g}, "
            f"{self.coverage:.0%} interval [{self.low:.4g}, {self.high:.4g}] "
            f"(n = {self.samples.size})"
        )


def _sample(comp: Component, centre: float, n: int, rng: np.random.Generator) -> np.ndarray:
    """Draw n values of an input from its assigned distribution (JCGM 101 6.4)."""
    u = comp.standard_uncertainty  # also rejects unknown distributions
    a = abs(comp.value)
    if comp.distribution == "normal":
        if math.isinf(comp.dof):
            return centre + u * rng.standard_normal(n)
        # scaled and shifted t, JCGM 101 6.4.9
        return centre + u * rng.standard_t(comp.dof, n)
    if comp.distribution == "rectangular":
        return rng.uniform(centre - a, centre + a, n)
    if comp.distribution == "triangular":
        return rng.triangular(centre - a, centre, centre + a, n)
    # u-shaped (arcsine) on [centre - a, centre + a], JCGM 101 6.4.6
    return centre + a * np.sin(np.pi * (rng.random(n) - 0.5))


def _evaluate(func: Callable[..., float], draws: Mapping[str, object], n: int) -> np.ndarray:
    """Evaluate the model on whole arrays if it supports them, else sample by sample."""
    try:
        y = np.asarray(func(**draws), dtype=float)
        if y.shape == (n,):
            return y
        if y.shape == () and not any(isinstance(v, np.ndarray) for v in draws.values()):
            return np.full(n, float(y))  # nothing sampled inside the model
    except (TypeError, ValueError):
        pass
    arrays = {k: v for k, v in draws.items() if isinstance(v, np.ndarray)}
    fixed = {k: v for k, v in draws.items() if k not in arrays}
    return np.fromiter(
        (func(**fixed, **{k: v[i] for k, v in arrays.items()}) for i in range(n)),
        dtype=float,
        count=n,
    )


def monte_carlo(
    func: Callable[..., float],
    values: Mapping[str, float],
    inputs: Mapping[str, Component],
    extra: Sequence[Component] = (),
    n: int = 200_000,
    seed: int | None = None,
    coverage: float = 0.95,
    correlation: Correlation | None = None,
) -> MonteCarloResult:
    """Propagate distributions through y = func(**values) by Monte Carlo (GUM Supplement 1).

    Arguments mirror `propagate`. Each input in `inputs` is sampled around
    its value in `values` from its own distribution: normal (Student t when
    `dof` is finite), rectangular, triangular or u-shaped. Components in
    `extra` are sampled around zero, multiplied by their sensitivity and added
    to y. Arguments not in `inputs` are held fixed.

    `func` is called once with numpy arrays when it supports them (plain
    arithmetic does); otherwise it is called once per sample, which is slower.

    Correlated inputs are sampled from a joint normal distribution, so every
    component named in a non-zero correlation must be normal with infinite dof.

    `seed` makes the result repeatable. JCGM 101 7.2.2 suggests n of at least
    10^4 / (1 - coverage), i.e. 200 000 for 95 %.
    """
    if not 0 < coverage < 1:
        raise ValueError("coverage must be between 0 and 1")
    if n < 2:
        raise ValueError("n must be at least 2")
    rng = np.random.default_rng(seed)

    # one list of (argument name or None, component, centre)
    entries = [(arg, comp, float(values[arg])) for arg, comp in inputs.items()]
    entries += [(None, comp, 0.0) for comp in extra]
    names = [comp.name for _, comp, _ in entries]
    matrix = correlation_matrix(names, _rename_correlation(correlation, inputs))

    correlated = [i for i in range(len(entries)) if np.any(np.delete(matrix[i], i) != 0)]
    for i in correlated:
        comp = entries[i][1]
        if comp.distribution != "normal" or not math.isinf(comp.dof):
            raise ValueError(
                f"Monte Carlo correlation needs normal inputs with infinite dof; "
                f"{comp.name!r} is {comp.distribution} with dof {comp.dof}"
            )

    sampled: dict[int, np.ndarray] = {}
    if correlated:
        sub = matrix[np.ix_(correlated, correlated)]
        z = rng.multivariate_normal(np.zeros(len(correlated)), sub, size=n, method="eigh")
        for col, i in enumerate(correlated):
            _, comp, centre = entries[i]
            sampled[i] = centre + comp.standard_uncertainty * z[:, col]
    for i, (_, comp, centre) in enumerate(entries):
        if i not in sampled:
            sampled[i] = _sample(comp, centre, n, rng)

    draws: dict[str, object] = dict(values)
    added = np.zeros(n)
    for i, (arg, comp, _) in enumerate(entries):
        if arg is None:
            added += comp.sensitivity * sampled[i]
        else:
            draws[arg] = sampled[i]
    y = _evaluate(func, draws, n) + added

    ordered = np.sort(y)
    q = int(coverage * n + 0.5)
    widths = ordered[q - 1 :] - ordered[: n - q + 1]
    r = int(np.argmin(widths))
    return MonteCarloResult(
        mean=float(y.mean()),
        standard_uncertainty=float(y.std(ddof=1)),
        low=float(ordered[r]),
        high=float(ordered[r + q - 1]),
        coverage=coverage,
        samples=y,
    )


def monte_carlo_budget(
    components: Sequence[Component],
    value: float = 0.0,
    correlation: Correlation | None = None,
    n: int = 200_000,
    seed: int | None = None,
    coverage: float = 0.95,
) -> MonteCarloResult:
    """Monte Carlo (JCGM 101) for a budget given as a list of components.

    The model is the linear one a budget table stands for:
    y = value + sum(c_i * delta_i), where each delta_i is drawn around zero
    from component i's distribution (Student t for a normal component with
    finite dof). Use it to check a `combine` result: the GUM method replaces
    each t-distributed input by a normal one and puts the extra width into k,
    so with few degrees of freedom the two can differ.
    """
    if not components:
        raise ValueError("budget is empty")
    return monte_carlo(
        lambda: value,
        {},
        {},
        extra=components,
        n=n,
        seed=seed,
        coverage=coverage,
        correlation=correlation,
    )


@dataclass(frozen=True)
class Agreement:
    """Outcome of `compare_with_monte_carlo` (JCGM 101:2008 clause 8).

    gum_low, gum_high: y -/+ U. mc_low, mc_high: the Monte Carlo interval.
    d_low, d_high: the absolute differences of the endpoints. delta: the
    numerical tolerance. agrees: both differences are at most delta.
    """

    gum_low: float
    gum_high: float
    mc_low: float
    mc_high: float
    d_low: float
    d_high: float
    delta: float
    n_dig: int

    @property
    def agrees(self) -> bool:
        return self.d_low <= self.delta and self.d_high <= self.delta


def numerical_tolerance(u: float, n_dig: int = 2) -> float:
    """Numerical tolerance delta of a standard uncertainty (JCGM 101:2008 7.9.2).

    Write u with n_dig significant digits as c x 10^l; then delta = 10^l / 2.
    Example: u = 0.0191 with n_dig = 2 is 19 x 10^-3, so delta = 0.0005.
    """
    if not u > 0 or not math.isfinite(u):
        raise ValueError("u must be a positive finite number")
    if n_dig < 1:
        raise ValueError("n_dig must be at least 1")
    c = float(f"{u:.{n_dig}g}")  # u rounded to n_dig significant digits
    exponent = math.floor(math.log10(c)) - (n_dig - 1)
    return 0.5 * 10.0**exponent


def compare_with_monte_carlo(
    y: float, result: Result, mc: MonteCarloResult, n_dig: int = 2
) -> Agreement:
    """Check a GUM interval y +/- U against a Monte Carlo interval (JCGM 101:2008 8.2).

    d_low = |y - U - y_low| and d_high = |y + U - y_high|. The GUM result is
    confirmed when both are at most delta, the numerical tolerance of the
    Monte Carlo u(y) to n_dig significant digits (`numerical_tolerance`).
    Both intervals must have the same coverage probability.
    """
    if not math.isclose(result.coverage, mc.coverage):
        raise ValueError(
            f"coverage differs: GUM {result.coverage:.0%}, Monte Carlo {mc.coverage:.0%}"
        )
    low, high = y - result.expanded, y + result.expanded
    return Agreement(
        gum_low=low,
        gum_high=high,
        mc_low=mc.low,
        mc_high=mc.high,
        d_low=abs(low - mc.low),
        d_high=abs(high - mc.high),
        delta=numerical_tolerance(mc.standard_uncertainty, n_dig),
        n_dig=n_dig,
    )
