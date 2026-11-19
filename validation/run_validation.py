"""Run every reference case in validation/cases and write validation/report.md.

    python validation/run_validation.py            # writes the report, exit code 1 on any fail
    python validation/run_validation.py --check    # same, but does not write the report

Each CSV in cases/ is named after the labqc function it checks and has one row per case:
inputs (JSON), the output compared, the expected value (JSON), the tolerance and its type
(abs or rel; blank = must match exactly), where the expected value comes from, and the
working. Expected values come from published examples, standard tables, or the cited
formula evaluated by hand; never from labqc itself.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))  # validate the code in this repository

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import scipy  # noqa: E402

import labqc  # noqa: E402
from labqc import conformity as cf  # noqa: E402
from labqc import control_charts as cc  # noqa: E402
from labqc import emissions as em  # noqa: E402
from labqc import proficiency as pt  # noqa: E402
from labqc import topdown as td  # noqa: E402
from labqc import uncertainty as unc  # noqa: E402
from labqc import validation as val  # noqa: E402

# Public functions that do no calculation of their own, and why they have no reference case.
NOT_VALIDATED = {
    "uncertainty.components_from_table": "input parsing; covered by unit tests",
    "uncertainty.correlation_matrix": "input checking; correlated results validated via combine",
    "emissions.register_gas": "configuration; conversions validated via ppm_to_mg_m3",
    "report.*": "records and file output, no calculation; covered by unit tests",
    "proficiency.robust_mean_sd": "no citable reference case yet: see TO_CHECK.md",
}

MODELS: dict[str, Callable[..., float]] = {
    "a*b": lambda a, b: a * b,
    "x1+x2+x3+x4": lambda x1, x2, x3, x4: x1 + x2 + x3 + x4,
}


def _dof(value) -> float:
    return math.inf if value in (None, "inf") else float(value)


def _components(rows: list[dict]) -> list[unc.Component]:
    return [
        unc.Component(
            r.get("name", f"c{i}"),
            r["value"],
            r.get("distribution", "normal"),
            r.get("k", 1.0),
            r.get("sensitivity", 1.0),
            _dof(r.get("dof")),
        )
        for i, r in enumerate(rows)
    ]


def _combine(i: dict) -> dict:
    corr = {(a, b): r for a, b, r in i.get("correlation", [])} or None
    r = unc.combine(_components(i["components"]), k=i.get("k"), correlation=corr)
    return {"u_c": r.combined, "U": r.expanded, "k": r.k, "v_eff": r.effective_dof}


def _propagate(i: dict) -> dict:
    inputs = {name: unc.Component(name, u) for name, u in i["u"].items()}
    y, r = unc.propagate(MODELS[i["model"]], i["values"], inputs)
    return {"y": y, "u_c": r.combined}


def _monte_carlo(i: dict) -> dict:
    names = ["x1", "x2", "x3", "x4"]
    comps = {n: unc.Component(n, i["half_width"], i["distribution"]) for n in names}
    r = unc.monte_carlo(
        MODELS[i["model"]], dict.fromkeys(names, 0.0), comps, n=i["n"], seed=i["seed"]
    )
    return {"u": r.standard_uncertainty, "low": r.low, "high": r.high, "mean": r.mean}


def _monte_carlo_budget(i: dict) -> dict:
    r = unc.monte_carlo_budget(
        _components(i["components"]), i.get("value", 0.0), n=i["n"], seed=i["seed"]
    )
    return {"u": r.standard_uncertainty, "low": r.low, "high": r.high, "mean": r.mean}


def _compare_with_monte_carlo(i: dict) -> dict:
    result = unc.combine(_components(i["components"]), k=i["k"])
    mc = unc.MonteCarloResult(i["mc_mean"], i["mc_u"], i["mc_low"], i["mc_high"], 0.95, np.empty(0))
    a = unc.compare_with_monte_carlo(i["y"], result, mc, n_dig=i["n_dig"])
    return {"d_low": a.d_low, "d_high": a.d_high, "delta": a.delta, "agrees": a.agrees}


def _decide(i: dict) -> dict:
    d = cf.decide(**i)
    return {
        "outcome": d.outcome,
        "acceptance_lower": d.acceptance_lower,
        "acceptance_upper": d.acceptance_upper,
        "probability": d.probability,
    }


def _u_bias(b: td.Bias) -> dict:
    return {"bias": b.bias, "u_ref": b.u_ref, "u_bias": b.u_bias}


def _combine_topdown(i: dict) -> dict:
    r = td.combine_topdown(i["u_rw"], i["u_bias"], k=i.get("k", 2.0))
    return {"u_c": r.combined, "U": r.expanded}


def _linearity(i: dict) -> dict:
    cal = val.linearity(i["x"], i["y"], weights=i.get("weights"))
    return {"slope": cal.slope, "intercept": cal.intercept, "r_squared": cal.r_squared}


def _lack_of_fit(i: dict) -> dict:
    r = val.lack_of_fit(i["x"], i["y"])
    return {"f": r.f, "dof_lack_of_fit": r.dof_lack_of_fit, "dof_pure_error": r.dof_pure_error}


def _lod_loq(i: dict) -> dict:
    lod, loq = val.lod_loq(val.linearity(i["x"], i["y"]), i.get("blank_sd"))
    return {"lod": lod, "loq": loq}


def _intermediate(i: dict) -> dict:
    df = pd.DataFrame([{"day": g, "value": v} for g, values in i["groups"].items() for v in values])
    r = val.intermediate_precision(df, "value", "day")
    return {
        "ms_between": r.ms_between,
        "ms_within": r.ms_within,
        "sd_repeatability": r.sd_repeatability,
        "sd_between": r.sd_between,
    }


def _trueness(i: dict) -> dict:
    r = val.trueness(i["results"], i["crm_value"], i["crm_u"])
    return {"t": r.t, "mean": r.mean, "U_bias": r.U_bias, "passed": r.passed}


def _pt_history(i: dict) -> dict:
    df = pd.DataFrame({"date": range(len(i["z"])), "z": i["z"]})
    h = pt.pt_history(df)
    return {
        "two_beyond_2_rounds": [int(n) + 1 for n in h.index[h["two_beyond_2"]]],
        "trend_9_rounds": [int(n) + 1 for n in h.index[h["trend_9"]]],
    }


def _westgard(i: dict) -> dict:
    t = cc.westgard(i["values"], cc.Limits(i["centre"], i["sd"]))
    last = t.iloc[-1]
    return {"rules_at_last": [r for r in ("1_2s", *cc.REJECT_RULES) if last[r]]}


def _westgard_levels(i: dict) -> dict:
    limits = {n: cc.Limits(c, s) for n, (c, s) in i["limits"].items()}
    t = cc.westgard_levels(i["values"], limits)
    last = t.iloc[-1]
    rules = [c for c in t.columns if not c.startswith("z_") and c != "status"]
    return {f"{r}_at_last": bool(last[r]) for r in rules}


def _cusum(i: dict) -> dict:
    t = cc.cusum(i["values"], i["target"], i["sd"], i["k"], i["h"])
    return {
        "c_plus_29": float(t.loc[28, "c_plus"]),
        "first_signal_observation": int(t.index[t["signal"]][0]) + 1,
    }


def _ewma(i: dict) -> dict:
    t = cc.ewma(i["values"], i["target"], i["sd"], i["lam"], i["L"])
    return {"ewma_1": t.loc[0, "ewma"], "ucl_1": t.loc[0, "ucl"], "ucl_last": t["ucl"].iloc[-1]}


def _correct_emission(i: dict) -> dict:
    r = em.correct_emission(**i)
    return {"mg_m3_ref": r.mg_m3_ref, "percent_of_limit": r.percent_of_limit}


ADAPTERS: dict[str, Callable[[dict], dict]] = {
    "uncertainty.standard_uncertainty": lambda i: {
        "u": unc.Component("x", i["value"], i["distribution"], i.get("k", 1.0)).standard_uncertainty
    },
    "uncertainty.type_a": lambda i: {
        "u": unc.type_a(i["readings"]).standard_uncertainty,
        "dof": unc.type_a(i["readings"]).dof,
    },
    "uncertainty.coverage_factor": lambda i: {
        "k": unc.coverage_factor(_dof(i["dof"]), i["coverage"])
    },
    "uncertainty.welch_satterthwaite": lambda i: {
        "v_eff": unc.welch_satterthwaite(_components(i["components"]))
    },
    "uncertainty.combine": _combine,
    "uncertainty.propagate": _propagate,
    "uncertainty.monte_carlo": _monte_carlo,
    "uncertainty.monte_carlo_budget": _monte_carlo_budget,
    "uncertainty.numerical_tolerance": lambda i: {"delta": unc.numerical_tolerance(**i)},
    "uncertainty.compare_with_monte_carlo": _compare_with_monte_carlo,
    "validation.linearity": _linearity,
    "validation.lack_of_fit": _lack_of_fit,
    "validation.lod_loq": _lod_loq,
    "validation.precision": lambda i: val.precision(i["values"]),
    "validation.recovery": lambda i: {"percent": val.recovery(**i)},
    "validation.intermediate_precision": _intermediate,
    "validation.trueness": _trueness,
    "proficiency.z_score": lambda i: {"z": pt.z_score(**i)},
    "proficiency.zeta_score": lambda i: {"zeta": pt.zeta_score(**i)},
    "proficiency.en_number": lambda i: {"en": pt.en_number(**i)},
    "proficiency.classify": lambda i: {"label": pt.classify(i["score"], i["kind"])},
    "proficiency.pt_history": _pt_history,
    "control_charts.limits_from_data": lambda i: (lambda lim: {"centre": lim.centre, "sd": lim.sd})(
        cc.limits_from_data(i["values"], i["method"])
    ),
    "control_charts.westgard": _westgard,
    "control_charts.westgard_levels": _westgard_levels,
    "control_charts.cusum": _cusum,
    "control_charts.ewma": _ewma,
    "emissions.ppm_to_mg_m3": lambda i: {"mg_m3": em.ppm_to_mg_m3(**i)},
    "emissions.mg_m3_to_ppm": lambda i: {"ppm": em.mg_m3_to_ppm(**i)},
    "emissions.to_reference_o2": lambda i: {"c_ref": em.to_reference_o2(**i)},
    "emissions.wet_to_dry": lambda i: {"dry": em.wet_to_dry(**i)},
    "emissions.to_temperature_pressure": lambda i: {"mg_m3_std": em.to_temperature_pressure(**i)},
    "emissions.correct_emission": _correct_emission,
    "emissions.percent_of_limit": lambda i: {"percent": em.percent_of_limit(**i)},
    "conformity.probability_of_conformance": lambda i: {"p": cf.probability_of_conformance(**i)},
    "conformity.decide": _decide,
    "conformity.guard_band": lambda i: {"w": cf.guard_band(**i)},
    "topdown.u_rw": lambda i: {"u_rw": td.u_rw(**i)},
    "topdown.s_r_duplicates": lambda i: {"s_r": td.s_r_duplicates(**i)},
    "topdown.u_bias_pt": lambda i: _u_bias(td.u_bias_pt(**i)),
    "topdown.u_bias_crm": lambda i: _u_bias(td.u_bias_crm(**i)),
    "topdown.combine_topdown": _combine_topdown,
    "emissions.corrected_uncertainty": lambda i: {"u_c": em.corrected_uncertainty(**i)[1].combined},
}


@dataclass
class Outcome:
    function: str
    case: str
    output: str
    expected: object
    got: object
    tolerance: str
    source_type: str
    source: str
    passed: bool
    note: str = ""


def _compare(expected, got, tol: str, kind: str) -> bool:
    if tol == "":
        return expected == got
    if isinstance(got, (bool, str, list)) or got is None:
        return False
    t = float(tol)
    diff = abs(float(got) - float(expected))
    return diff <= (t if kind == "abs" else t * abs(float(expected)))


def run_cases() -> list[Outcome]:
    outcomes = []
    for path in sorted((HERE / "cases").glob("*.csv")):
        function = path.stem
        adapter = ADAPTERS.get(function)
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                expected = json.loads(row["expected"])
                tol, kind = row["tolerance"], row["tolerance_type"]
                tol_text = (
                    "exact" if tol == "" else f"± {tol}" + (" (rel)" if kind == "rel" else "")
                )
                base = dict(
                    function=function,
                    case=row["case"],
                    output=row["output"],
                    expected=expected,
                    tolerance=tol_text,
                    source_type=row["source_type"],
                    source=row["source"],
                )
                if adapter is None:
                    outcomes.append(Outcome(got=None, passed=False, note="no adapter", **base))
                    continue
                try:
                    got = adapter(json.loads(row["inputs"]))[row["output"]]
                except Exception as err:  # a crash is a failed case, reported, not raised
                    outcomes.append(
                        Outcome(got=None, passed=False, note=f"{type(err).__name__}: {err}", **base)
                    )
                    continue
                if isinstance(got, (np.floating, np.integer)):
                    got = got.item()
                if isinstance(got, np.bool_):
                    got = bool(got)
                outcomes.append(Outcome(got=got, passed=_compare(expected, got, tol, kind), **base))
    return outcomes


def public_functions() -> list[str]:
    import inspect

    names = []
    for module in (
        "uncertainty",
        "validation",
        "proficiency",
        "control_charts",
        "emissions",
        "conformity",
        "topdown",
    ):
        mod = getattr(labqc, module)
        for name, obj in vars(mod).items():
            if name.startswith("_") or not inspect.isfunction(obj):
                continue
            if obj.__module__ == mod.__name__:
                names.append(f"{module}.{name}")
    names.append("uncertainty.standard_uncertainty")  # Component property
    return sorted(set(names))


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "src"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        return out.stdout.strip() + (" (src has uncommitted changes)" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _cell(text: object) -> str:
    """Text safe inside a Markdown table cell."""
    return str(text).replace("|", r"\|").replace("\n", " ")


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:.10g}"
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value) + "]" if value else "none"
    return _cell(value)


def report(outcomes: list[Outcome]) -> str:
    passed = sum(o.passed for o in outcomes)
    failed = len(outcomes) - passed
    covered = sorted({o.function for o in outcomes})
    missing = [
        f
        for f in public_functions()
        if f not in covered
        and f not in NOT_VALIDATED
        and f.split(".")[0] + ".*" not in NOT_VALIDATED
    ]
    now = datetime.now(timezone.utc).replace(microsecond=0)
    lines = [
        "# labqc validation report",
        "",
        f"**Result: {'PASS' if failed == 0 else 'FAIL'}**: {passed} of {len(outcomes)} reference "
        f"cases passed across {len(covered)} functions.",
        "",
        "| | |",
        "|---|---|",
        f"| labqc version | {labqc.__version__} |",
        f"| Git commit | {_git_commit()} |",
        f"| Python | {platform.python_version()} ({platform.system()} {platform.machine()}) |",
        f"| numpy / scipy / pandas | {np.__version__} / {scipy.__version__} / {pd.__version__} |",
        f"| Date (UTC) | {now.isoformat()} |",
        "",
        "Each case compares a labqc result with a reference value within a stated tolerance. "
        "Reference values come from published worked examples, standard tables, the cited "
        "formula evaluated by hand, or the definition of a rule; never from labqc itself. "
        "Inputs, references and the working for every case are in `validation/cases/`. "
        "Generated by `validation/run_validation.py`; CI runs it on every push and fails on "
        "any failed case.",
        "",
        "Source types: "
        + ", ".join(
            f"{t} ({sum(o.source_type == t for o in outcomes)})"
            for t in sorted({o.source_type for o in outcomes})
        )
        + ".",
        "",
    ]
    if failed:
        lines += [
            "## Failed cases",
            "",
            "| Function | Case | Expected | Got | Note |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| `{o.function}` | {_cell(o.case)} | {_fmt(o.expected)} | {_fmt(o.got)} | "
            f"{_cell(o.note)} |"
            for o in outcomes
            if not o.passed
        ]
        lines.append("")
    module = None
    for o in outcomes:
        mod = o.function.split(".")[0]
        if mod != module:
            module = mod
            lines += [
                f"## {mod}",
                "",
                "| Function | Case | Output | Expected | Got | Tolerance | Result | Source |",
                "|---|---|---|---|---|---|---|---|",
            ]
        lines.append(
            f"| `{o.function.split('.', 1)[1]}` | {_cell(o.case)} | {o.output} | "
            f"{_fmt(o.expected)} | {_fmt(o.got)} | {o.tolerance} | "
            f"{'pass' if o.passed else '**FAIL**'} | {_cell(o.source)} ({o.source_type}) |"
        )
        if o is outcomes[-1] or outcomes[outcomes.index(o) + 1].function.split(".")[0] != mod:
            lines.append("")
    lines += ["## Not validated by reference cases", "", "| Function | Reason |", "|---|---|"]
    lines += [f"| `{f}` | {why} |" for f, why in NOT_VALIDATED.items()]
    lines += [f"| `{f}` | **no reference case yet** |" for f in missing]
    lines += [
        "",
        "Open questions about sources (clause numbers, editions, cases still to add) are listed "
        "in `validation/TO_CHECK.md`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="do not write report.md")
    args = parser.parse_args()
    outcomes = run_cases()
    if not args.check:
        (HERE / "report.md").write_text(report(outcomes), encoding="utf-8")
    failed = [o for o in outcomes if not o.passed]
    print(f"labqc {labqc.__version__}: {len(outcomes) - len(failed)}/{len(outcomes)} cases passed")
    for o in failed:
        print(f"FAIL {o.function} | {o.case} | expected {o.expected} got {o.got} {o.note}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
