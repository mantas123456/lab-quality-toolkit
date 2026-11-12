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
