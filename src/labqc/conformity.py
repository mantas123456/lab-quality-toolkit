"""Decision rules: stating conformity with a specification when the result has an uncertainty.

Concepts follow ILAC G8:09/2019 and JCGM 106:2012; the explanations here are my own words.

A specification gives tolerance limits (TL): a lower limit, an upper limit, or both. The
measured value y carries an expanded uncertainty U (usually k = 2, about 95 %). Where y lies
relative to a limit, and how close, decides how much risk a "pass" or "fail" statement
carries. A decision rule fixes that in advance by choosing acceptance limits (AL):

simple       Acceptance limits equal the tolerance limits (guard band w = 0). Pass when y is
             inside the limits, fail otherwise. Near a limit the risk of a wrong pass is up to
             50 %, so this rule suits cases where U is small compared with the tolerance.
guarded      A guard band w (often w = U) moves the acceptance limits inside the tolerance
             limits, and a rejection limit the same distance outside. Inside the acceptance
             limits: pass; beyond the rejection limits: fail; in between, no clear decision.
             The risk of a wrong pass or a wrong fail is then small (about 2.5 % or less for
             w = U with k = 2), at the price of results that cannot be decided.
non-binary   The same guard band, but the zones are named: pass, conditional pass (inside
             the tolerance limit, but within w of it), conditional fail (outside, but within
             w), fail.

`probability_of_conformance` gives the probability that the true value lies inside the
tolerance limits, given y and its standard uncertainty u (JCGM 106, normal or t).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy import stats

RULES = ("simple", "guarded", "non-binary")


def guard_band(U: float, r: float = 1.0) -> float:
    """Guard band w = r * U. r = 1 is the usual choice; r = 0 gives simple acceptance."""
    if U < 0 or r < 0:
        raise ValueError("U and r must not be negative")
    return r * U


def probability_of_conformance(
    value: float,
    u: float,
    lower: float | None = None,
    upper: float | None = None,
    dof: float = math.inf,
) -> float:
    """Probability that the measurand lies within [lower, upper] (JCGM 106:2012, 7.2-7.3).

    The state of knowledge about the measurand is a normal distribution with mean `value`
    and standard deviation u, or a scaled and shifted t-distribution when `dof` is finite.
    Give at least one limit; a missing limit is open.
    """
    if lower is None and upper is None:
        raise ValueError("give a lower limit, an upper limit or both")
    if lower is not None and upper is not None and lower >= upper:
        raise ValueError("the lower limit must be below the upper limit")
    if not u > 0:
        raise ValueError("u must be greater than 0")
    dist = stats.norm() if math.isinf(dof) else stats.t(dof)
    p_upper = 1.0 if upper is None else float(dist.cdf((upper - value) / u))
    p_lower = 0.0 if lower is None else float(dist.cdf((lower - value) / u))
    return p_upper - p_lower


@dataclass(frozen=True)
class Decision:
    """Outcome of `decide`.

    outcome: "pass", "fail", "conditional pass", "conditional fail" or "no clear decision".
    accepted: True for pass (and conditional pass), False for fail (and conditional fail),
        None for no clear decision.
    acceptance_lower / acceptance_upper: the acceptance limits used (None = open).
    rejection_lower / rejection_upper: beyond these the result fails (guarded and
        non-binary rules; equal to the tolerance limits for simple acceptance).
    probability: probability of conformance with the tolerance limits (u = U / k).
    wording: suggested neutral sentence for the report.
    """

    value: float
    U: float
    k: float
    lower: float | None
    upper: float | None
    rule: str
    guard_band: float
    outcome: str
    accepted: bool | None
    acceptance_lower: float | None
    acceptance_upper: float | None
    rejection_lower: float | None
    rejection_upper: float | None
    probability: float
    wording: str


def _fmt(x: float) -> str:
    return f"{x:.4g}"


def decide(
    value: float,
    U: float,
    lower: float | None = None,
    upper: float | None = None,
    rule: str = "simple",
    guard_band: float | None = None,
    k: float = 2.0,
    unit: str = "",
) -> Decision:
    """State conformity of `value` (expanded uncertainty U, coverage factor k) with limits.

    rule: "simple", "guarded" or "non-binary" (see the module docstring). For the guarded
    and non-binary rules, `guard_band` is w in the units of the value; None means w = U.
    For simple acceptance the guard band is 0 and `guard_band` must be None or 0.
    """
    if rule not in RULES:
        raise ValueError(f"rule must be one of {', '.join(RULES)}")
    if lower is None and upper is None:
        raise ValueError("give a lower limit, an upper limit or both")
    if lower is not None and upper is not None and lower >= upper:
        raise ValueError("the lower limit must be below the upper limit")
    if U < 0:
        raise ValueError("U must not be negative")
    if not k > 0:
        raise ValueError("k must be greater than 0")
    if rule == "simple":
        if guard_band:
            raise ValueError("simple acceptance has no guard band; use rule='guarded'")
        w = 0.0
    else:
        w = U if guard_band is None else float(guard_band)
        if w < 0:
            raise ValueError("the guard band must not be negative")
    if lower is not None and upper is not None and 2 * w >= upper - lower:
        raise ValueError("the guard band leaves no acceptance zone between the limits")

    acc_lo = None if lower is None else lower + w
    acc_hi = None if upper is None else upper - w
    rej_lo = None if lower is None else lower - w
    rej_hi = None if upper is None else upper + w

    inside_tolerance = (lower is None or value >= lower) and (upper is None or value <= upper)
    inside_acceptance = (acc_lo is None or value >= acc_lo) and (acc_hi is None or value <= acc_hi)
    inside_rejection = (rej_lo is None or value >= rej_lo) and (rej_hi is None or value <= rej_hi)

    if inside_acceptance:
        outcome, accepted = "pass", True
    elif not inside_rejection:  # with w = 0 (simple) every value is in one of these two
        outcome, accepted = "fail", False
    elif rule == "guarded":
        outcome, accepted = "no clear decision", None
    elif inside_tolerance:
        outcome, accepted = "conditional pass", True
    else:
        outcome, accepted = "conditional fail", False

    u = U / k
    if u > 0:
        probability = probability_of_conformance(value, u, lower, upper)
    else:
        probability = 1.0 if inside_tolerance else 0.0

    return Decision(
        value=value,
        U=U,
        k=k,
        lower=lower,
        upper=upper,
        rule=rule,
        guard_band=w,
        outcome=outcome,
        accepted=accepted,
        acceptance_lower=acc_lo,
        acceptance_upper=acc_hi,
        rejection_lower=rej_lo,
        rejection_upper=rej_hi,
        probability=probability,
        wording=_wording(value, U, k, lower, upper, rule, w, outcome, unit),
    )


def _limits_text(lower: float | None, upper: float | None, unit: str) -> str:
    u = f" {unit}" if unit else ""
    if lower is not None and upper is not None:
        return f"{_fmt(lower)} to {_fmt(upper)}{u}"
    if upper is not None:
        return f"at most {_fmt(upper)}{u}"
    return f"at least {_fmt(lower)}{u}"


def _wording(value, U, k, lower, upper, rule, w, outcome, unit) -> str:
    u = f" {unit}" if unit else ""
    result = (
        f"The result is {_fmt(value)}{u} with an expanded uncertainty of {_fmt(U)}{u} (k = {k:g})."
    )
    spec = f"the specification ({_limits_text(lower, upper, unit)})"
    if rule == "simple":
        rule_text = "Decision rule: simple acceptance (ILAC G8:09/2019), no guard band."
    else:
        name = "guarded acceptance and rejection" if rule == "guarded" else "non-binary statement"
        rule_text = f"Decision rule: {name} with a guard band of {_fmt(w)}{u} (ILAC G8:09/2019)."
    statement = {
        "pass": f"The result conforms to {spec}.",
        "fail": f"The result does not conform to {spec}.",
        "conditional pass": (
            f"The measured value is within {spec}, but closer to the limit than the guard "
            "band: conformity is stated conditionally (conditional pass)."
        ),
        "conditional fail": (
            f"The measured value is outside {spec}, but within the guard band of the limit: "
            "non-conformity is stated conditionally (conditional fail)."
        ),
        "no clear decision": (
            f"The result lies within the guard band of a limit, so no statement of conformity "
            f"with {spec} can be made under this rule."
        ),
    }[outcome]
    return f"{result} {statement} {rule_text}"
