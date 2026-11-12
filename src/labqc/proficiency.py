"""Proficiency-testing performance statistics (ISO 13528:2022, ISO/IEC 17043).

z     = (x - x_pt) / sigma_pt
zeta  = (x - x_pt) / sqrt(u_x^2 + u_pt^2)
E_n   = (x - x_pt) / sqrt(U_x^2 + U_pt^2)      (expanded uncertainties)

z and zeta: |score| <= 2 satisfactory, 2 < |score| < 3 questionable,
|score| >= 3 unsatisfactory. E_n: |E_n| <= 1 satisfactory, otherwise not.
"""

from __future__ import annotations

import math

import numpy as np


def z_score(x: float, assigned: float, sigma_pt: float) -> float:
    return (x - assigned) / sigma_pt


def zeta_score(x: float, assigned: float, u_x: float, u_assigned: float) -> float:
    return (x - assigned) / math.sqrt(u_x**2 + u_assigned**2)


def en_number(x: float, assigned: float, U_x: float, U_assigned: float) -> float:
    return (x - assigned) / math.sqrt(U_x**2 + U_assigned**2)


def classify(score: float, kind: str = "z") -> str:
    """Interpret a score. kind is "z" (also for zeta) or "en"."""
    s = round(abs(score), 9)  # avoid floating-point noise at the 2 and 3 boundaries
    if kind == "en":
        return "satisfactory" if s <= 1 else "unsatisfactory"
    if s <= 2:
        return "satisfactory"
    return "questionable" if s < 3 else "unsatisfactory"


def robust_mean_sd(values, tol: float = 1e-6, max_iter: int = 100) -> tuple[float, float]:
    """Algorithm A from ISO 13528 Annex C: robust mean and standard deviation.

    Useful when the assigned value is the consensus of participants.
    """
    x = np.asarray(values, dtype=float)
    mean = float(np.median(x))
    sd = 1.483 * float(np.median(np.abs(x - mean)))
    for _ in range(max_iter):
        delta = 1.5 * sd
        clipped = np.clip(x, mean - delta, mean + delta)
        new_mean = float(clipped.mean())
        new_sd = 1.134 * float(clipped.std(ddof=1))
        if abs(new_mean - mean) < tol and abs(new_sd - sd) < tol:
            return new_mean, new_sd
        mean, sd = new_mean, new_sd
    return mean, sd
