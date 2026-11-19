"""Plain-English "What this means" sentences under each result in the web app.

Each function takes results that labqc already calculated and returns at most two short,
factual sentences. They read numbers back and compare them with the stated criteria; they
calculate nothing new and give no advice beyond what the numbers show.
"""

from __future__ import annotations

import math

import pandas as pd


def _pct(share: float) -> str:
    """A share of variance as a percentage that never rounds a small share to 0 %."""
    if share >= 0.995:
        return f"{share:.2%}"
    return f"{share:.0%}" if share >= 0.1 else f"{share:.1%}"


def uncertainty(
    table: pd.DataFrame, k: float, effective_dof: float, covariance: float
) -> list[str]:
    """`table` is Result.table (sorted, largest share first)."""
    top = table.iloc[0]
    first = f"{top['component']} gives {_pct(top['share_of_variance'])} of the variance."
    if len(table) > 1:
        second = table.iloc[1]
        if top["share_of_variance"] >= 0.8:
            first += (
                f" The next largest, {second['component']}, gives "
                f"{_pct(second['share_of_variance'])}: reducing it would barely change U."
            )
        else:
            first += f" {second['component']} follows with {_pct(second['share_of_variance'])}."
    if covariance:
        effect = "raise" if covariance > 0 else "lower"
        second_sentence = (
            f"The correlations between inputs {effect} u_c: their covariance terms add "
            f"{covariance:+.3g} to u_c²."
        )
    elif math.isinf(effective_dof):
        second_sentence = (
            f"Every component has infinite degrees of freedom, so k = {k:.2f} "
            "comes from the normal distribution."
        )
    elif k > 2.1:
        second_sentence = (
            f"k is {k:.2f}, not 2, because the budget has only {effective_dof:.1f} effective "
            "degrees of freedom; a fixed k = 2 would understate U."
        )
    else:
        second_sentence = (
            f"With {effective_dof:.1f} effective degrees of freedom, k = {k:.2f} is close to 2."
        )
    return [first, second_sentence]


def monte_carlo(
    agrees: bool, d_low: float, d_high: float, delta: float, n_dig: int, finite_dof: bool
) -> list[str]:
    """`finite_dof`: some input has finite degrees of freedom."""
    worst = max(d_low, d_high)
    if agrees:
        return [
            f"Both interval ends agree within δ = {delta:.2g} "
            f"(largest difference {worst:.2g}), so the GUM interval is confirmed "
            f"to {n_dig} significant digit{'s' if n_dig > 1 else ''} (JCGM 101 clause 8).",
        ]
    return [
        f"An interval end differs by {worst:.2g}, more than δ = {delta:.2g}, so the GUM "
        f"interval is not confirmed to {n_dig} significant digit{'s' if n_dig > 1 else ''}.",
        "Monte Carlo samples inputs with few degrees of freedom from a t-distribution "
        "instead of widening k, which can move the interval ends."
        if finite_dof
        else "The difference comes from the shape of the input distributions, which the "
        "GUM method replaces by a normal distribution for y.",
    ]


def validation(
    r_squared: float,
    lack_of_fit_p: float | None,
    lack_of_fit_significant: bool | None,
    lod: float,
    loq: float,
    recovery_percent: float,
) -> list[str]:
    if lack_of_fit_p is None:
        fit = (
            f"The line explains R² = {r_squared:.4f} of the signal variation; "
            "add replicate standards to test for lack of fit."
        )
    elif lack_of_fit_significant:
        fit = (
            f"The lack-of-fit test is significant (p = {lack_of_fit_p:.3f}): the straight line "
            "does not describe the standards within their repeatability."
        )
    else:
        fit = (
            f"The lack-of-fit test finds no significant departure from the line "
            f"(p = {lack_of_fit_p:.3f}), with R² = {r_squared:.4f}."
        )
    limits = (
        f"Results below LOD = {lod:.3g} cannot be told apart from a blank, and below "
        f"LOQ = {loq:.3g} they are not precise enough to quantify; recovery is "
        f"{recovery_percent:.1f} % of the amount added."
    )
    return [fit, limits]


def pt_scores(z: float, z_label: str, en: float, en_label: str) -> list[str]:
    first = f"z = {z:.2f} is {z_label}: your result is {abs(z):.2f} σ_pt from the assigned value."
    if en_label == "satisfactory":
        second = (
            f"|En| = {abs(en):.2f} ≤ 1: the difference is covered by the two expanded "
            "uncertainties."
        )
    else:
        second = (
            f"|En| = {abs(en):.2f} > 1: the difference is larger than the two expanded "
            "uncertainties allow."
        )
    return [first, second]


def pt_round(round_table: pd.DataFrame, robust_mean: float, robust_sd: float) -> list[str]:
    n = len(round_table)
    bad = round_table[round_table["status"] == "unsatisfactory"]["lab"].tolist()
    first = (
        f"The robust mean of the {n} labs is {robust_mean:.4g} with a robust SD of "
        f"{robust_sd:.3g}; Algorithm A limits the pull of extreme results."
    )
    if bad:
        second = f"{_join(bad)} {'is' if len(bad) == 1 else 'are'} unsatisfactory (|z| ≥ 3)."
    else:
        second = "No lab is unsatisfactory (|z| ≥ 3)."
    return [first, second]


def pt_history(history: pd.DataFrame) -> list[str]:
    n = len(history)
    action = history[history["action"]]
    if action.empty:
        return [
            f"None of the {n} rounds needs action: no unsatisfactory score and no warning signal."
        ]
    reasons = []
    for _, row in action.iterrows():
        why = [
            label
            for flag, label in (
                (row["classification"] == "unsatisfactory", "unsatisfactory"),
                (row["two_beyond_2"], "two rounds in a row beyond |z| = 2"),
                (row["trend_9"], "nine rounds on one side"),
            )
            if flag
        ]
        reasons.append(f"{row['date']} ({', '.join(why)})")
    return [
        f"{len(action)} of the {n} rounds need action: {'; '.join(reasons)}.",
        "Two rounds beyond 2 or a run on one side points to a bias that single scores hide.",
    ]


def westgard(table: pd.DataFrame, x_name: str, rules: tuple[str, ...]) -> list[str]:
    """`table` is the app's status table: first column x, plus status and rule columns."""
    rejects = table[table["status"] == "reject"]
    n_warn = int((table["status"] == "warning").sum())
    if rejects.empty:
        if n_warn:
            return [f"No run is rejected; {n_warn} warning(s) need a check but no action."]
        return ["No run is rejected and there are no warnings."]
    first = rejects.iloc[0]
    reject_rules = [r for r in rules if r != "1_2s"]
    at_first = [r for r in reject_rules if bool(first[r])]
    broken = [r for r in reject_rules if bool(rejects[r].any())]
    systematic = [r for r in broken if r in SYSTEMATIC_RULES]
    random = [r for r in broken if r not in SYSTEMATIC_RULES]
    parts = []
    if systematic:
        parts.append(
            f"{_join(systematic)} {_verb(systematic)} to systematic error, such as calibration"
        )
    if random:
        verb = "" if systematic else f" {_verb(random)}"
        parts.append(f"{_join(random)}{verb} to random error")
    return [
        f"{len(rejects)} run(s) are rejected, the first at {x_name} {first.iloc[0]} "
        f"by {', '.join(at_first)}.",
        "; ".join(parts) + ".",
    ]


def _verb(rules: list[str]) -> str:
    return "points" if len(rules) == 1 else "point"


# Westgard rules that point to systematic error; 1_3s and R_4s point to random error.
SYSTEMATIC_RULES = frozenset({"2_2s", "4_1s", "10_x", "2of3_2s", "3_1s", "12_x"})


def cusum(table: pd.DataFrame, x_name: str, h: float) -> list[str]:
    hits = table[table["signal"]]
    if hits.empty:
        return [f"Neither cumulative sum passes h = {h:g}: no shift is detected."]
    first = hits.iloc[0]
    side = "an upward" if first["signal_high"] else "a downward"
    return [
        f"The CUSUM first signals at {x_name} {first.iloc[0]}: {side} shift, "
        f"{len(hits)} point(s) beyond h = {h:g} in all.",
        "CUSUM adds up small deviations, so it finds shifts of about 1 SD that single "
        "Westgard rules can miss.",
    ]


def ewma(table: pd.DataFrame, x_name: str, lam: float) -> list[str]:
    hits = table[table["signal"]]
    if hits.empty:
        return [f"The EWMA (λ = {lam:g}) stays inside its limits: no drift is detected."]
    first = hits.iloc[0]
    side = "above the upper" if first["ewma"] > first["ucl"] else "below the lower"
    return [
        f"The EWMA first goes {side} limit at {x_name} {first.iloc[0]}, "
        f"with {len(hits)} point(s) outside in all.",
        f"With λ = {lam:g} each point carries {lam:.0%} of the weight, so the chart reacts "
        "to slow drifts rather than single outliers.",
    ]


def emissions(table: pd.DataFrame, correction_factor: float, o2_ref: float) -> list[str]:
    if correction_factor > 1:
        first = (
            f"The flue gas holds more O₂ than the reference {o2_ref:g} %, so readings are "
            f"diluted and are multiplied by {correction_factor:.3f}."
        )
    elif correction_factor < 1:
        first = (
            f"The flue gas holds less O₂ than the reference {o2_ref:g} %, so readings are "
            f"multiplied by {correction_factor:.3f}."
        )
    else:
        first = f"Measured O₂ equals the reference {o2_ref:g} %, so no O₂ correction applies."
    limited = table.dropna(subset=["% of limit"])
    if limited.empty:
        return [first]
    over = limited[limited["result"] == "FAIL"]
    if over.empty:
        second = "Every gas with a limit is below it after correction."
    else:
        parts = [f"{g} ({p:.0f} %)" for g, p in zip(over["gas"], over["% of limit"], strict=True)]
        second = f"Above the limit after correction: {_join(parts)}."
    return [first, second]


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


RULE_NAMES = {
    "simple": "simple acceptance",
    "guarded": "guarded acceptance and rejection",
    "non-binary": "the non-binary rule",
}


def decision(outcome: str, rule: str, probability: float, guard_band: float) -> list[str]:
    """For a labqc.conformity.Decision: what the outcome means, and its probability."""
    name = RULE_NAMES[rule]
    first = {
        "pass": f"Under {name} the result passes: it lies inside the acceptance limits.",
        "fail": f"Under {name} the result fails: it lies outside the rejection limits.",
        "conditional pass": (
            f"Under {name} the result is a conditional pass: inside the specification, but "
            f"within the guard band ({guard_band:.3g}) of a limit."
        ),
        "conditional fail": (
            f"Under {name} the result is a conditional fail: outside the specification, but "
            f"within the guard band ({guard_band:.3g}) of a limit."
        ),
        "no clear decision": (
            f"Under {name} no decision can be stated: the result lies within the guard band "
            f"({guard_band:.3g}) of a limit."
        ),
    }[outcome]
    second = (
        f"The probability that the true value is within the specification is {probability:.1%}."
    )
    if rule == "simple" and 0.05 < probability < 0.95:
        second += (
            " Simple acceptance does not use U, so this close to a limit the decision can be wrong."
        )
    return [first, second]


def topdown(table, relative: bool, expanded: float, k: float, source: str) -> list[str]:
    """For a labqc.topdown.TopDownResult: which term dominates, and what U covers."""
    rw = float(table.iloc[0]["share_of_variance"])
    unit = " %" if relative else ""
    if rw >= 0.5:
        first = (
            f"Within-lab reproducibility gives {_pct(rw)} of u_c²: day-to-day scatter, not bias, "
            "sets the uncertainty."
        )
    else:
        first = (
            f"The bias terms give {_pct(1 - rw)} of u_c²: the {source} results, not "
            "day-to-day scatter, set the uncertainty."
        )
    second = (
        f"U = {expanded:.3g}{unit} (k = {k:g}) applies to routine results like the control sample "
        f"and the {source} samples, measured with this method."
    )
    return [first, second]
