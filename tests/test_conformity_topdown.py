"""Decision rules (labqc.conformity) and top-down uncertainty (labqc.topdown).

Expected values are hand calculations from the formulas in the module docstrings, or
standard-normal and Student-t table values.
"""

import math

import pytest

from labqc.conformity import RULES, decide, guard_band, probability_of_conformance
from labqc.topdown import combine_topdown, s_r_duplicates, u_bias_crm, u_bias_pt, u_rw

# --- probability of conformance -----------------------------------------------------


def test_probability_one_sided_is_phi():
    assert probability_of_conformance(9.5, 0.5, upper=10) == pytest.approx(0.841345, abs=1e-6)
    assert probability_of_conformance(10.5, 0.5, lower=10) == pytest.approx(0.841345, abs=1e-6)


def test_probability_two_sided():
    """Value in the middle of [8, 12] with u = 1: P = Phi(2) - Phi(-2) = 0.9545."""
    assert probability_of_conformance(10, 1, 8, 12) == pytest.approx(0.954500, abs=1e-6)


def test_probability_with_t_distribution():
    """t(0.975, 4) = 2.776445: one-sided probability 0.975."""
    assert probability_of_conformance(0, 1, upper=2.776445, dof=4) == pytest.approx(0.975, abs=1e-6)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"value": 1, "u": 1}, "give a lower limit"),
        ({"value": 1, "u": 1, "lower": 2, "upper": 1}, "lower limit must be below"),
        ({"value": 1, "u": 0, "upper": 2}, "u must be greater than 0"),
    ],
)
def test_probability_errors(kwargs, message):
    with pytest.raises(ValueError, match=message):
        probability_of_conformance(**kwargs)


# --- decide -------------------------------------------------------------------------

# upper limit 10, U = 1 (k = 2), guard band w = U = 1: acceptance limit 9, rejection limit 11
OUTCOMES = {
    "simple": ["pass", "pass", "pass", "fail", "fail"],
    "guarded": ["pass", "no clear decision", "no clear decision", "no clear decision", "fail"],
    "non-binary": ["pass", "conditional pass", "conditional pass", "conditional fail", "fail"],
}
VALUES = [8.0, 9.2, 9.9, 10.4, 11.5]


@pytest.mark.parametrize("rule", RULES)
def test_decide_zones(rule):
    got = [decide(v, 1.0, upper=10, rule=rule).outcome for v in VALUES]
    assert got == OUTCOMES[rule]


def test_decide_limits_and_probability():
    d = decide(9.2, 1.0, upper=10, rule="non-binary")
    assert (d.acceptance_upper, d.rejection_upper, d.guard_band) == (9.0, 11.0, 1.0)
    assert d.acceptance_lower is None and d.accepted is True
    assert d.probability == pytest.approx(0.945201, abs=1e-6)  # Phi(0.8 / 0.5) = Phi(1.6)


def test_decide_two_sided_and_custom_guard_band():
    d = decide(5.6, 0.4, lower=4.0, upper=6.0, rule="guarded", guard_band=0.2)
    assert (d.acceptance_lower, d.acceptance_upper) == pytest.approx((4.2, 5.8))
    assert d.outcome == "pass"
    low = decide(4.1, 0.4, lower=4.0, upper=6.0, rule="guarded", guard_band=0.2)
    assert low.outcome == "no clear decision" and low.accepted is None


def test_decide_value_on_the_limit_passes_simple_acceptance():
    assert decide(10.0, 1.0, upper=10).outcome == "pass"


def test_decide_wording_is_neutral_and_complete():
    d = decide(10.4, 1.0, upper=10, rule="non-binary", unit="mg/kg")
    assert d.wording.startswith(
        "The result is 10.4 mg/kg with an expanded uncertainty of 1 mg/kg (k = 2)."
    )
    assert "conditional fail" in d.wording
    assert "guard band of 1 mg/kg" in d.wording
    assert "at most 10 mg/kg" in d.wording
    simple = decide(8.0, 1.0, lower=5, upper=10).wording
    assert "conforms to the specification (5 to 10)" in simple
    assert "simple acceptance" in simple


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"rule": "lenient"}, "rule must be one of"),
        ({"upper": None}, "give a lower limit"),
        ({"rule": "simple", "guard_band": 0.5}, "simple acceptance has no guard band"),
        ({"rule": "guarded", "guard_band": -1}, "must not be negative"),
        ({"lower": 9.5, "rule": "guarded"}, "leaves no acceptance zone"),
        ({"U": -1}, "U must not be negative"),
    ],
)
def test_decide_errors(kwargs, message):
    args = {"value": 9.8, "U": 1.0, "upper": 10.0, **kwargs}
    with pytest.raises(ValueError, match=message):
        decide(**args)


def test_guard_band():
    assert guard_band(2.0) == 2.0
    assert guard_band(2.0, 1.5) == 3.0
    with pytest.raises(ValueError):
        guard_band(-1.0)


# --- top-down -----------------------------------------------------------------------


def test_u_rw_from_control_series():
    assert u_rw([1, 2, 3, 4]) == pytest.approx(1.290994, abs=1e-6)
    assert u_rw([1, 2, 3, 4], relative=True) == pytest.approx(51.63978, abs=1e-5)  # / 2.5
    assert u_rw([1, 2, 3, 4], s_r=1.0) == pytest.approx(math.sqrt(5 / 3 + 1))


def test_s_r_from_duplicates():
    """Differences -1, 1, -2: sqrt(6 / 6) = 1; mean |d| / 1.128 = 1.3333 / 1.128."""
    first, second = [10, 20, 30], [11, 19, 32]
    assert s_r_duplicates(first, second) == pytest.approx(1.0)
    assert s_r_duplicates(first, second, method="range") == pytest.approx(1.182033, abs=1e-6)
    rel = s_r_duplicates([100, 200], [102, 196], relative=True)
    d = [100 * -2 / 101, 100 * 4 / 198]
    assert rel == pytest.approx(math.sqrt((d[0] ** 2 + d[1] ** 2) / 4))


def test_u_bias_from_pt():
    """Biases 0.5, -0.2, 0.2: RMS = sqrt(0.33 / 3); u(Cref) = mean(0.1, 0.2, 0.3) = 0.2."""
    b = u_bias_pt([10.5, 9.8, 10.2], [10, 10, 10], [0.1, 0.2, 0.3])
    assert b.bias == pytest.approx(math.sqrt(0.11))
    assert b.u_ref == pytest.approx(0.2)
    assert b.u_bias == pytest.approx(math.sqrt(0.15))
    rel = u_bias_pt([10.5, 19.6], [10, 20], [0.1, 0.4], relative=True)
    assert rel.bias == pytest.approx(math.sqrt((5**2 + 2**2) / 2))  # 5 % and -2 %
    assert rel.u_ref == pytest.approx(1.5)  # mean of 1 % and 2 %


def test_u_bias_from_crm():
    """b = 0.2, s = 0.1, n = 3, u(Cref) = 0.05: sqrt(0.04 + 0.01 / 3 + 0.0025)."""
    b = u_bias_crm([10.1, 10.3, 10.2], certified=10.0, u_certified=0.05)
    assert b.bias == pytest.approx(0.2)
    assert b.s_bias == pytest.approx(0.1)
    assert b.u_bias == pytest.approx(math.sqrt(0.04 + 0.01 / 3 + 0.0025))
    rel = u_bias_crm([10.1, 10.3, 10.2], certified=10.0, u_certified=0.05, relative=True)
    assert rel.u_bias == pytest.approx(10 * b.u_bias)  # percent of 10


def test_combine_topdown():
    r = combine_topdown(3.0, 4.0)
    assert (r.combined, r.k, r.expanded) == pytest.approx((5.0, 2.0, 10.0))
    assert r.table["share_of_variance"].tolist() == pytest.approx([0.36, 0.64])
    pt = u_bias_pt([10.5, 9.8, 10.2], [10, 10, 10], [0.1, 0.2, 0.3])
    r = combine_topdown(0.3, pt)
    assert r.u_bias == pytest.approx(math.sqrt(0.15))
    assert r.table["share_of_variance"].sum() == pytest.approx(1.0)
    assert "U (k = 2)" in str(r)


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: u_rw([1.0]), "at least 2"),
        (lambda: s_r_duplicates([1, 2], [1, 2, 3]), "same number"),
        (lambda: s_r_duplicates([1, 2], [1, 3], method="iqr"), "method must be"),
        (lambda: u_bias_pt([1, 2], [1], [0.1]), "equal length"),
        (lambda: u_bias_crm([1, 2], 0.0, 0.1, relative=True), "certified value other than 0"),
        (lambda: combine_topdown(-1, 1), "must not be negative"),
    ],
)
def test_topdown_errors(call, message):
    with pytest.raises(ValueError, match=message):
        call()
