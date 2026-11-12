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

from collections.abc import Sequence
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
