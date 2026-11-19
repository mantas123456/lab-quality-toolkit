"""Outlier tests, method comparison, inverse prediction and equipment drift (v1.4).

Expected values are hand calculations from the formulas in the module docstrings, the
Miller & Miller calibration example, or Grubbs critical values from ISO 5725-2.
"""

import math
from datetime import date

import numpy as np
import pytest

from labqc.comparison import bland_altman, deming, passing_bablok
from labqc.equipment import drift
from labqc.outliers import (
    cochran,
    cochran_critical,
    grubbs,
    grubbs_critical,
    grubbs_two,
    grubbs_two_critical,
)
from labqc.validation import inverse_prediction, linearity

# --- outliers -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "c95", "c99"), [(4, 1.481, 1.496), (5, 1.715, 1.764), (10, 2.290, 2.482)]
)
def test_grubbs_critical_values_match_iso_5725_2(n, c95, c99):
    assert grubbs_critical(n, 0.05) == pytest.approx(c95, abs=0.0006)
    assert grubbs_critical(n, 0.01) == pytest.approx(c99, abs=0.0006)


def test_grubbs_statistic_by_hand():
    """Values 1, 2, 3, 4, 10: mean 4, s = sqrt(50 / 4); G = 6 / s = 1.6971."""
    t = grubbs([1, 2, 3, 4, 10])
    assert t.statistic == pytest.approx(6 / math.sqrt(12.5))
    assert (t.suspect, t.index, t.side) == ((10.0,), (4,), "high")
    assert t.label == "ok"  # 1.697 < 1.715 (n = 5, 5 %)


def test_grubbs_labels():
    assert grubbs([10.1, 10.3, 9.9, 10.2, 10.0, 11.4]).label == "straggler"
    assert grubbs([10.1, 10.3, 9.9, 10.2, 10.0, 10.15, 10.05, 13.0]).label == "outlier"
    low = grubbs([10.1, 10.3, 9.9, 10.2, 10.0, 10.15, 10.05, 7.0])
    assert low.side == "low" and low.label == "outlier"


def test_grubbs_two_statistic_by_hand():
    """Values 1, 2, 3, 9, 10: mean 5, S_0 = 70; without 9 and 10, S = 2; G = 2 / 70."""
    t = grubbs_two([1, 2, 3, 9, 10])
    assert t.statistic == pytest.approx(2 / 70)
    assert (t.suspect, t.side) == ((9.0, 10.0), "high")


def test_grubbs_two_critical_values_are_two_sided():
    """Simulated; ISO 5725-2 Table 5 gives about 0.0090 / 0.0018 (n = 5)."""
    c95, c99 = grubbs_two_critical(5)
    assert c95 == pytest.approx(0.0090, abs=0.001)
    assert c99 == pytest.approx(0.0018, abs=0.0005)
    assert grubbs_two([10.0, 10.1, 9.9, 10.2, 9.8, 10.05, 12.0, 12.1]).label == "outlier"


def test_cochran_statistic_by_hand():
    """Duplicates with variances d^2 / 2: 0.02, 0.005, 0.405, 0.02, 0.00125."""
    t = cochran([[1, 1.2], [2, 2.1], [3, 3.9], [4, 4.2], [5, 5.05]])
    total = 0.02 + 0.005 + 0.405 + 0.02 + 0.00125
    assert t.statistic == pytest.approx(0.405 / total)
    assert t.index == (2,) and t.n == 5
    assert t.critical_95 == pytest.approx(cochran_critical(5, 2, 0.05))


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: grubbs([1, 2]), "at least 3"),
        (lambda: grubbs([2, 2, 2]), "nothing to test"),
        (lambda: grubbs_two([1, 2, 3]), "at least 4"),
        (lambda: cochran([[1, 2], [1, 2, 3]]), "same number"),
        (lambda: cochran([[1, 2]]), "at least 2 groups"),
    ],
)
def test_outlier_errors(call, message):
    with pytest.raises(ValueError, match=message):
        call()


# --- method comparison --------------------------------------------------------------


def test_bland_altman_by_hand():
    """d = 0.1, 0.3, -0.1, 0.2: bias 0.125, s_d = sqrt(0.0875 / 3)."""
    ba = bland_altman([1, 2, 3, 4], [1.1, 2.3, 2.9, 4.2])
    sd = math.sqrt(0.0875 / 3)
    assert ba.bias == pytest.approx(0.125)
    assert ba.sd == pytest.approx(sd)
    assert ba.loa == pytest.approx((0.125 - 1.96 * sd, 0.125 + 1.96 * sd))
    t = 3.182446  # t(0.975, 3)
    assert ba.bias_ci95 == pytest.approx((0.125 - t * sd / 2, 0.125 + t * sd / 2), abs=1e-6)
    half = t * sd * math.sqrt(3 / 4)
    assert ba.upper_ci95 == pytest.approx((ba.loa[1] - half, ba.loa[1] + half), abs=1e-6)


def test_deming_by_hand():
    """x = 0, 1, 2; y = 0, 2, 1: Sxx = Syy = 2, Sxy = 1, ratio 1: slope 1, intercept 0."""
    line = deming([0, 1, 2], [0, 2, 1])
    assert (line.slope, line.intercept) == pytest.approx((1.0, 0.0))


def test_deming_exact_line_and_ratio():
    x = np.array([1.0, 2.0, 4.0, 7.0])
    for ratio in (0.25, 1.0, 4.0):
        line = deming(x, 2 * x + 1, error_ratio=ratio)
        assert (line.slope, line.intercept) == pytest.approx((2.0, 1.0))
    # a very large ratio (x almost error-free) approaches ordinary least squares
    rng = np.random.default_rng(0)
    xs = np.linspace(1, 10, 20)
    ys = 1.1 * xs + rng.normal(0, 0.3, 20)
    ols = np.polyfit(xs, ys, 1)[0]
    assert deming(xs, ys, error_ratio=1e9).slope == pytest.approx(ols, rel=1e-6)


def test_deming_interval_contains_the_true_line():
    rng = np.random.default_rng(1)
    truth = np.linspace(5, 50, 40)
    x = truth + rng.normal(0, 0.5, 40)
    y = 1.0 * truth + rng.normal(0, 0.5, 40)
    line = deming(x, y)
    assert line.slope_ci95[0] < 1 < line.slope_ci95[1]
    assert line.agrees


def test_passing_bablok_by_hand():
    """Slopes 2, 0.5, 4/3, (-1 left out), 1, 3: median of 5 is 4/3; a = median(y - b x)."""
    line = passing_bablok([1, 2, 3, 4], [1, 3, 2, 5])
    assert line.slope == pytest.approx(4 / 3)
    assert line.intercept == pytest.approx(-1 / 3)


def test_passing_bablok_is_robust_and_detects_curvature():
    x = np.arange(1, 31, dtype=float)
    y = 1.05 * x + 0.2
    y[5] = 80  # one gross outlier barely moves the line
    line = passing_bablok(x, y)
    assert line.slope == pytest.approx(1.05, abs=1e-9)
    assert line.linear
    curved = passing_bablok(x, 0.02 * x**2 + x)
    assert not curved.linear


def test_comparison_errors():
    with pytest.raises(ValueError, match="same number"):
        bland_altman([1, 2, 3], [1, 2])
    with pytest.raises(ValueError, match="error ratio"):
        deming([1, 2, 3], [1, 2, 3], error_ratio=0)


# --- inverse prediction -------------------------------------------------------------

MM_X = [0, 2, 4, 6, 8, 10, 12]
MM_Y = [2.1, 5.0, 9.0, 12.6, 17.3, 21.0, 24.7]


@pytest.mark.parametrize(
    ("y0", "x0", "u"), [(2.9, 0.72, 0.26), (13.5, 6.21, 0.24), (23.0, 11.13, 0.26)]
)
def test_inverse_prediction_miller_miller(y0, x0, u):
    """Miller & Miller fluorescence example: b = 1.93, a = 1.52, s_y/x = 0.4329."""
    r = inverse_prediction(linearity(MM_X, MM_Y), [y0])
    assert r.x0 == pytest.approx(x0, abs=0.005)
    assert r.u_x0 == pytest.approx(u, abs=0.005)
    assert r.dof == 5


def test_inverse_prediction_replicates_narrow_the_interval():
    cal = linearity(MM_X, MM_Y)
    one = inverse_prediction(cal, [13.5])
    three = inverse_prediction(cal, [13.4, 13.5, 13.6])
    assert three.x0 == pytest.approx(one.x0)
    assert three.u_x0 < one.u_x0
    lo, hi = one.interval()
    assert lo < one.x0 < hi


def test_inverse_prediction_rejects_weighted_lines():
    with pytest.raises(ValueError, match="unweighted"):
        inverse_prediction(linearity(MM_X[1:], MM_Y[1:], weights="1/x"), [10.0])


# --- equipment drift ----------------------------------------------------------------


def test_drift_by_hand_and_shorten():
    """2000-01-01 to 2004-01-01 is exactly 4 x 365.25 days. Errors 0.10 then 0.18: drift
    0.02 per year. |e| + U = 0.3 at 0.10 + 0.02 T = 0.25, T = 7.5 years, 3.5 after the last
    certificate, inside the 4-year interval: shorten to 3.5 years."""
    d = drift(["2000-01-01", "2004-01-01"], [0.10, 0.18], U=0.05, tolerance=0.3)
    assert d.drift_per_year == pytest.approx(0.02)
    assert d.t_reach_years == pytest.approx(3.5)
    assert d.interval_years == pytest.approx(4.0)
    assert d.suggestion == "shorten"
    assert d.suggested_interval_years == pytest.approx(3.5)
    assert d.reach_date == date(2007, 7, 2)  # 3.5 x 365.25 = 1278.4 days after 2004-01-01


def test_drift_keep_and_lengthen():
    dates = ["2019-01-10", "2020-01-12", "2021-01-15", "2022-01-10", "2023-01-11"]
    keep = drift(dates, [0.02, 0.05, 0.07, 0.10, 0.12], U=0.05, tolerance=0.3)
    assert keep.suggestion == "keep"
    stable = drift(dates, [0.01, 0.0, 0.01, 0.01, 0.0], U=0.03, tolerance=0.3)
    assert stable.suggestion == "lengthen"
    assert stable.suggested_interval_years == pytest.approx(1.5 * stable.interval_years)


def test_drift_negative_and_already_out():
    down = drift(["2000-01-01", "2004-01-01"], [-0.10, -0.18], U=0.05, tolerance=0.3)
    assert down.t_reach_years == pytest.approx(3.5)
    out = drift(["2000-01-01", "2004-01-01"], [0.10, 0.28], U=0.05, tolerance=0.3)
    assert out.t_reach_years == 0.0 and out.suggestion == "shorten"


def test_drift_errors():
    with pytest.raises(ValueError, match="in order"):
        drift(["2004-01-01", "2000-01-01"], [0.1, 0.2], 0.05, 0.3)
    with pytest.raises(ValueError, match="one error per"):
        drift(["2000-01-01", "2004-01-01"], [0.1], 0.05, 0.3)
    with pytest.raises(ValueError, match="tolerance"):
        drift(["2000-01-01", "2004-01-01"], [0.1, 0.2], 0.05, 0)
