import numpy as np
import pytest

from labqc.proficiency import classify, en_number, robust_mean_sd, z_score, zeta_score
from labqc.validation import linearity, lod_loq, precision, recovery


def test_perfect_line():
    cal = linearity([0, 1, 2, 3, 4], [1, 3, 5, 7, 9])
    assert cal.slope == pytest.approx(2)
    assert cal.intercept == pytest.approx(1)
    assert cal.r_squared == pytest.approx(1)
    assert cal.predict_concentration(6) == pytest.approx(2.5)


def test_lod_loq_ratio_and_blank_override():
    cal = linearity([0, 1, 2, 3, 4, 5], [0.1, 2.0, 4.2, 5.9, 8.1, 9.9])
    lod, loq = lod_loq(cal)
    assert loq / lod == pytest.approx(10 / 3.3)
    assert lod_loq(cal, blank_sd=0.2)[0] == pytest.approx(3.3 * 0.2 / cal.slope)


def test_precision_and_recovery():
    p = precision([10, 10, 10, 12])
    assert p["mean"] == pytest.approx(10.5)
    assert p["rsd_percent"] == pytest.approx(100 * 1 / 10.5)
    assert recovery(measured=14.5, unspiked=5.0, added=10.0) == pytest.approx(95.0)


@pytest.mark.parametrize(
    "score,kind,expected",
    [
        (1.9, "z", "satisfactory"),
        (-2.5, "z", "questionable"),
        (3.0, "z", "unsatisfactory"),
        (0.9, "en", "satisfactory"),
        (-1.2, "en", "unsatisfactory"),
    ],
)
def test_classify(score, kind, expected):
    assert classify(score, kind) == expected


def test_scores():
    assert z_score(10.6, 10.0, 0.3) == pytest.approx(2.0)
    assert zeta_score(10.6, 10.0, 0.3, 0.4) == pytest.approx(1.2)
    assert en_number(10.6, 10.0, 0.6, 0.8) == pytest.approx(0.6)


def test_algorithm_a_resists_outliers():
    rng = np.random.default_rng(1)
    clean = rng.normal(50, 1, 40)
    mean, sd = robust_mean_sd(np.append(clean, [80, 85]))
    assert mean == pytest.approx(clean.mean(), abs=0.3)
    assert 0.7 < sd < 1.4


def test_boundary_is_not_affected_by_float_noise():
    assert classify(z_score(10.6, 10.0, 0.3)) == "satisfactory"


# --- v0.3: validation ----------------------------------------------------------

MM_CONC = [0, 2, 4, 6, 8, 10]
MM_ABS = [0.009, 0.158, 0.301, 0.472, 0.577, 0.739]
MM_SD = np.array([0.001, 0.004, 0.010, 0.013, 0.017, 0.022])


def test_weighted_regression_miller_and_miller():
    """Miller & Miller, Statistics and Chemometrics for Analytical Chemistry, weighted
    regression worked example (section 5.10): weights 1/s^2 give slope 0.0738 and
    intercept 0.0091; the unweighted line is slope 0.0725, intercept 0.0133."""
    from labqc.validation import linearity

    ols = linearity(MM_CONC, MM_ABS)
    assert ols.slope == pytest.approx(0.0725, abs=5e-5)
    assert ols.intercept == pytest.approx(0.0133, abs=5e-5)
    weighted = linearity(MM_CONC, MM_ABS, weights=1 / MM_SD**2)
    assert weighted.weighting == "custom"
    assert weighted.slope == pytest.approx(0.0738, abs=5e-5)
    assert weighted.intercept == pytest.approx(0.0091, abs=5e-5)
    assert weighted.weighted_residuals.shape == (6,)


def test_weighted_regression_named_weights():
    """Hand check: points exactly on y = 2x + 1 give the same line for any weighting,
    and 1/x weighting refuses a zero concentration."""
    from labqc.validation import linearity

    for w in ("1/x", "1/x^2"):
        cal = linearity([1, 2, 4, 8], [3, 5, 9, 17], weights=w)
        assert cal.slope == pytest.approx(2)
        assert cal.intercept == pytest.approx(1)
        assert cal.weighting == w
    with pytest.raises(ValueError):
        linearity([0, 1, 2], [0, 1, 2], weights="1/x")


def test_lack_of_fit_hand_calculation():
    """Hand calculation: x = 1,1,2,2,3,3 and y = 1,3,4,6,4,6. The line y = 1 + 1.5x
    leaves SS_res = 9; replicates give SS_pe = 6 (3 dof), so SS_lof = 3 (1 dof) and
    F = (3/1) / (6/3) = 1.5, p = 0.308 from F(1, 3)."""
    from labqc.validation import lack_of_fit, linearity

    lof = lack_of_fit([1, 1, 2, 2, 3, 3], [1, 3, 4, 6, 4, 6])
    assert lof.f == pytest.approx(1.5)
    assert (lof.dof_lack_of_fit, lof.dof_pure_error) == (1, 3)
    assert lof.p_value == pytest.approx(0.308, abs=1e-3)
    assert not lof.significant
    assert linearity([1, 1, 2, 2, 3, 3], [1, 3, 4, 6, 4, 6]).lack_of_fit == lof
    assert lack_of_fit([1, 2, 3], [1, 2, 3]) is None  # no replicates


def test_intermediate_precision_one_way_anova():
    """Miller & Miller one-way ANOVA example (fluorescence of a solution stored under
    four conditions, three replicates each): MS_between = 62, MS_within = 3, F = 20.7.
    Then s_r = sqrt(3) and s_between = sqrt((62 - 3) / 3)."""
    import pandas as pd

    from labqc.validation import intermediate_precision

    df = pd.DataFrame(
        {
            "day": list("AAABBBCCCDDD"),
            "value": [102, 100, 101, 101, 101, 104, 97, 95, 99, 90, 92, 94],
        }
    )
    ip = intermediate_precision(df, "value", "day")
    assert ip.ms_between == pytest.approx(62)
    assert ip.ms_within == pytest.approx(3)
    assert ip.f == pytest.approx(20.67, abs=0.01)
    assert ip.sd_repeatability == pytest.approx(3**0.5)
    assert ip.sd_between == pytest.approx((59 / 3) ** 0.5)
    assert ip.sd_intermediate == pytest.approx((3 + 59 / 3) ** 0.5)
    assert ip.rsd_intermediate_percent == pytest.approx(100 * ip.sd_intermediate / 98)


def test_trueness_t_test_and_erm_criterion():
    """Miller & Miller, comparison of a mean with a known value: five results 50.4, 50.7,
    49.1, 49.0, 51.1 against 50 give mean 50.06, s = 0.956 and t = 0.14 (not significant).
    The pass/fail follows ERM Application Note 1: |bias| <= 2 sqrt(s^2/n + u_crm^2)."""
    from labqc.validation import trueness

    res = trueness([50.4, 50.7, 49.1, 49.0, 51.1], crm_value=50, crm_u=0.2)
    assert res.mean == pytest.approx(50.06)
    assert res.sd == pytest.approx(0.956, abs=1e-3)
    assert res.t == pytest.approx(0.14, abs=5e-3)
    assert res.p_value > 0.05
    assert res.U_bias == pytest.approx(2 * (0.9555**2 / 5 + 0.2**2) ** 0.5, rel=1e-3)
    assert res.passed
    # a clear bias with a tight CRM fails
    assert not trueness([51.0, 51.1, 50.9], crm_value=50, crm_u=0.05).passed


# --- v0.3: proficiency history -------------------------------------------------


def test_pt_history_flags():
    """Rules as documented in pt_history: two successive |z| > 2 (the 2_2s idea applied
    to PT rounds) and nine rounds on one side of zero (Nelson's rule 2, J. Qual. Technol.
    16 (1984) 237). Hand-built series: rounds 3-4
    are two questionable scores in a row; rounds 5-13 are nine small positive scores."""
    import pandas as pd

    from labqc.proficiency import pt_history

    z = [0.3, -0.5, 2.4, -2.2, 0.1, 0.4, 0.8, 0.2, 1.1, 0.6, 0.3, 0.9, 0.5, -3.1]
    dates = pd.date_range("2024-01-01", periods=len(z), freq="QS")
    shuffled = pd.DataFrame({"date": dates, "z": z}).sample(frac=1, random_state=0)
    h = pt_history(shuffled)
    assert list(h["z"]) == z  # sorted back into date order
    assert h.index[h["two_beyond_2"]].tolist() == [3]
    assert h.index[h["trend_9"]].tolist() == [12]
    assert h.loc[13, "classification"] == "unsatisfactory"
    assert h.index[h["action"]].tolist() == [3, 12, 13]


def test_predict_signal_on_fitted_line():
    """Hand check: y = 2x + 1 gives 9 at x = 4, and predict_concentration inverts it."""
    from labqc.validation import linearity

    cal = linearity([0, 1, 2, 3], [1, 3, 5, 7])
    assert cal.predict_signal(4) == pytest.approx(9)
    assert list(cal.predict_signal([0, 2])) == pytest.approx([1, 5])
    assert cal.predict_concentration(cal.predict_signal(2.5)) == pytest.approx(2.5)
