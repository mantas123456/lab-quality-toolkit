"""Internal quality control: Shewhart limits and Westgard multirules.

Rules are evaluated on z = (x - target) / sd for one control material:

1_2s  warning   one result beyond 2 SD
1_3s  reject    one result beyond 3 SD (random error)
2_2s  reject    two consecutive results beyond 2 SD on the same side (systematic)
R_4s  reject    consecutive results differ by more than 4 SD, one above +2 SD and
                one below -2 SD (random error)
4_1s  reject    four consecutive results beyond 1 SD on the same side (systematic)
10_x  reject    ten consecutive results on the same side of the target (systematic)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

REJECT_RULES = ("1_3s", "2_2s", "R_4s", "4_1s", "10_x")


@dataclass(frozen=True)
class Limits:
    centre: float
    sd: float

    def line(self, n_sd: float) -> float:
        return self.centre + n_sd * self.sd


def limits_from_data(values: Sequence[float], method: str = "sd") -> Limits:
    """Estimate the centre line and SD from a baseline run.

    method "sd" uses the sample standard deviation; "moving_range" uses the
    average moving range / 1.128, which is less inflated by drifts.
    """
    x = np.asarray(values, dtype=float)
    if method == "moving_range":
        sd = float(np.mean(np.abs(np.diff(x))) / 1.128)
    elif method == "sd":
        sd = float(x.std(ddof=1))
    else:
        raise ValueError("method must be 'sd' or 'moving_range'")
    return Limits(float(x.mean()), sd)


def _run_same_side(z: np.ndarray, threshold: float, length: int) -> np.ndarray:
    """True where the last `length` points are all beyond `threshold` on one side."""
    hit = np.zeros(z.size, dtype=bool)
    for i in range(length - 1, z.size):
        w = z[i - length + 1 : i + 1]
        if (w > threshold).all() or (w < -threshold).all():
            hit[i] = True
    return hit


def westgard(values: Sequence[float], limits: Limits) -> pd.DataFrame:
    """Flag each result with the Westgard rules it violates.

    Returns a table with the value, its z-score, one boolean column per rule,
    and a status: "accept", "warning" (1_2s only) or "reject".
    """
    x = np.asarray(values, dtype=float)
    z = (x - limits.centre) / limits.sd
    prev = np.concatenate([[np.nan], z[:-1]])
    rules = {
        "1_2s": np.abs(z) > 2,
        "1_3s": np.abs(z) > 3,
        "2_2s": _run_same_side(z, 2, 2),
        "R_4s": ((z > 2) & (prev < -2)) | ((z < -2) & (prev > 2)),
        "4_1s": _run_same_side(z, 1, 4),
        "10_x": _run_same_side(z, 0, 10),
    }
    out = pd.DataFrame({"value": x, "z": z.round(3), **rules})
    reject = out[list(REJECT_RULES)].any(axis=1)
    out["status"] = np.where(reject, "reject", np.where(out["1_2s"], "warning", "accept"))
    return out


def _same_side(window: np.ndarray, threshold: float) -> bool:
    return bool(window.size) and bool((window > threshold).all() or (window < -threshold).all())


def westgard_levels(
    values: Mapping[str, Sequence[float]], limits: Mapping[str, Limits]
) -> pd.DataFrame:
    """Westgard multirules across two or three control materials run together.

    `values` maps each control level (e.g. "low", "high") to its results,
    one per run; `limits` gives each level its own centre and SD. Rules use
    z-scores, so levels with different concentrations can be compared.

    Two levels: 1_3s, 2_2s (both levels in one run, or one level in two
    runs), R_4s (one level above +2 SD and the other below -2 SD in one run),
    4_1s (two runs x two levels, or one level over four runs), 10_x (five
    runs x two levels, or one level over ten runs).

    Three levels: 1_3s, 2of3_2s (two of the three in one run beyond 2 SD on
    the same side), R_4s, 3_1s (all three in one run, or one level over three
    runs), 12_x (four runs x three levels, or one level over twelve runs).

    Returns one row per run: z per level, one boolean column per rule and a
    status ("accept", "warning" for 1_2s only, or "reject"), like `westgard`.
    """
    names = list(values)
    if len(names) not in (2, 3):
        raise ValueError("westgard_levels needs two or three control levels")
    if set(limits) != set(names):
        raise ValueError("limits must have one entry per control level")
    lengths = {len(values[n]) for n in names}
    if len(lengths) != 1:
        raise ValueError("every level needs one result per run")
    z = np.column_stack(
        [(np.asarray(values[n], dtype=float) - limits[n].centre) / limits[n].sd for n in names]
    )
    runs, levels = z.shape

    def across(threshold: float, count: int) -> np.ndarray:
        """`count` consecutive results beyond threshold on one side, across levels
        (the last count / levels runs together) or within one level over runs."""
        span = count // levels
        hit = np.zeros(runs, dtype=bool)
        for i in range(runs):
            if i + 1 >= span and _same_side(z[i + 1 - span : i + 1].ravel(), threshold):
                hit[i] = True
            elif i + 1 >= count and any(
                _same_side(z[i + 1 - count : i + 1, j], threshold) for j in range(levels)
            ):
                hit[i] = True
        return hit

    rules: dict[str, np.ndarray] = {
        "1_2s": (np.abs(z) > 2).any(axis=1),
        "1_3s": (np.abs(z) > 3).any(axis=1),
    }
    if levels == 2:
        rules["2_2s"] = across(2, 2)
    else:
        rules["2of3_2s"] = ((z > 2).sum(axis=1) >= 2) | ((z < -2).sum(axis=1) >= 2)
    rules["R_4s"] = (z.max(axis=1) > 2) & (z.min(axis=1) < -2)
    if levels == 2:
        rules["4_1s"] = across(1, 4)
        rules["10_x"] = across(0, 10)
    else:
        rules["3_1s"] = across(1, 3)
        rules["12_x"] = across(0, 12)

    out = pd.DataFrame({f"z_{n}": z[:, j].round(3) for j, n in enumerate(names)})
    for rule, hit in rules.items():
        out[rule] = hit
    reject = out[[r for r in rules if r != "1_2s"]].any(axis=1)
    out["status"] = np.where(reject, "reject", np.where(out["1_2s"], "warning", "accept"))
    return out


def cusum(
    values: Sequence[float], target: float, sd: float, k: float = 0.5, h: float = 5.0
) -> pd.DataFrame:
    """Tabular CUSUM in SD units (Montgomery, Introduction to Statistical Quality Control).

    C+_i = max(0, z_i - k + C+_{i-1}) and C-_i = max(0, -z_i - k + C-_{i-1}),
    with z = (x - target) / sd. A signal when either exceeds h. k = 0.5 and
    h = 5 detect a 1 SD shift quickly; smaller shifts than Westgard catches.

    Columns: value, z, c_plus, c_minus, signal_high, signal_low, signal.
    """
    x = np.asarray(values, dtype=float)
    z = (x - target) / sd
    c_plus = np.zeros(x.size)
    c_minus = np.zeros(x.size)
    up = down = 0.0
    for i, zi in enumerate(z):
        up = max(0.0, zi - k + up)
        down = max(0.0, -zi - k + down)
        c_plus[i], c_minus[i] = up, down
    out = pd.DataFrame(
        {
            "value": x,
            "z": z,
            "c_plus": c_plus,
            "c_minus": c_minus,
            "signal_high": c_plus > h,
            "signal_low": c_minus > h,
        }
    )
    out["signal"] = out["signal_high"] | out["signal_low"]
    return out


def ewma(
    values: Sequence[float], target: float, sd: float, lam: float = 0.2, L: float = 3.0
) -> pd.DataFrame:
    """EWMA chart (Montgomery, Introduction to Statistical Quality Control).

    ewma_i = lam * x_i + (1 - lam) * ewma_{i-1}, starting at the target, with
    exact limits target +/- L * sd * sqrt(lam / (2 - lam) * (1 - (1 - lam)^(2i))).

    Columns: value, ewma, lcl, ucl, signal.
    """
    if not 0 < lam <= 1:
        raise ValueError("lam must be in (0, 1]")
    x = np.asarray(values, dtype=float)
    smoothed = np.zeros(x.size)
    prev = target
    for i, xi in enumerate(x):
        prev = lam * xi + (1 - lam) * prev
        smoothed[i] = prev
    i = np.arange(1, x.size + 1)
    width = L * sd * np.sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * i)))
    out = pd.DataFrame({"value": x, "ewma": smoothed, "lcl": target - width, "ucl": target + width})
    out["signal"] = (out["ewma"] > out["ucl"]) | (out["ewma"] < out["lcl"])
    return out


OVERVIEW_COLUMNS = (
    "method", "level", "n", "limits_from", "baseline_n", "centre", "sd", "last_date",
    "last_value", "last_z", "status", "rules", "warnings", "rejects",
)  # fmt: skip


def qc_overview(
    data: pd.DataFrame,
    baseline: int = 20,
    method: str = "sd",
    date_col: str = "date",
    value_col: str = "value",
) -> pd.DataFrame:
    """Westgard status of the latest run for every method and control level in one table.

    `data` has one row per control result with columns method, level, date and value,
    and optionally target and sd. A series with a target and sd is checked against them
    from its first result; otherwise its first `baseline` results set the limits
    (`limits_from_data` with `method`) and the rest are checked. Rules are applied to each
    series on its own (see `westgard_levels` for rules across levels).

    Returns one row per series, in order of first appearance: method, level, n,
    limits_from, baseline_n, centre, sd, last_date, last_value, last_z, status (of the
    latest run: accept, warning or reject), rules (broken at the latest run), and the
    number of warnings and rejects among the checked runs.
    """
    needed = {"method", "level", date_col, value_col}
    missing = sorted(needed - set(data.columns))
    if missing:
        raise ValueError(f"The QC table needs the column(s): {', '.join(missing)}")
    rows = data.dropna(subset=["method", "level", value_col])
    if rows.empty:
        raise ValueError("The QC table has no results")
    has_limits = {"target", "sd"} <= set(rows.columns)
    out = []
    for (name, level), series in rows.groupby(["method", "level"], sort=False):
        series = series.sort_values(date_col, kind="stable")
        values = pd.to_numeric(series[value_col], errors="raise").to_numpy()
        target = series["target"].dropna() if has_limits else pd.Series(dtype=float)
        sd = series["sd"].dropna() if has_limits else pd.Series(dtype=float)
        if len(target) and len(sd):
            limits, n_base, source = Limits(float(target.iloc[0]), float(sd.iloc[0])), 0, "target"
        else:
            if len(values) <= baseline:
                raise ValueError(
                    f"{name} / {level}: {len(values)} results; needs more than the {baseline} "
                    "baseline results, or a target and sd"
                )
            limits = limits_from_data(values[:baseline], method)
            n_base, source = baseline, f"first {baseline} results"
        if not limits.sd > 0:
            raise ValueError(f"{name} / {level}: the SD must be greater than 0")
        table = westgard(values[n_base:], limits)
        last = table.iloc[-1]
        broken = [r for r in ("1_2s", *REJECT_RULES) if bool(last[r])]
        out.append(
            {
                "method": name,
                "level": level,
                "n": len(values),
                "limits_from": source,
                "baseline_n": n_base,
                "centre": limits.centre,
                "sd": limits.sd,
                "last_date": series[date_col].iloc[-1],
                "last_value": float(last["value"]),
                "last_z": float(last["z"]),
                "status": last["status"],
                "rules": ", ".join(broken),
                "warnings": int((table["status"] == "warning").sum()),
                "rejects": int((table["status"] == "reject").sum()),
            }
        )
    return pd.DataFrame(out, columns=list(OVERVIEW_COLUMNS))
