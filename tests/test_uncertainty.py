import math

import pytest

from labqc.uncertainty import Component, combine, coverage_factor, type_a, welch_satterthwaite


def test_distribution_divisors():
    assert Component("r", 0.1, "rectangular").standard_uncertainty == pytest.approx(0.057735, 1e-5)
    assert Component("t", 0.6, "triangular").standard_uncertainty == pytest.approx(
        0.6 / math.sqrt(6)
    )
    assert Component("cert", 0.2, "normal", k=2).standard_uncertainty == pytest.approx(0.1)


def test_sensitivity_coefficient_scales_contribution():
    assert Component("a", 0.5, sensitivity=-3).contribution == pytest.approx(1.5)


def test_combined_is_root_sum_of_squares():
    r = combine([Component("a", 3), Component("b", 4)], k=2)
    assert r.combined == pytest.approx(5)
    assert r.expanded == pytest.approx(10)
    assert r.table["share_of_variance"].sum() == pytest.approx(1)


def test_type_a():
    c = type_a([10, 11, 12])
    assert c.standard_uncertainty == pytest.approx(1 / math.sqrt(3))
    assert c.dof == 2


def test_welch_satterthwaite_and_k():
    comps = [Component("A", 1.0, dof=4), Component("B", 1.0)]
    assert welch_satterthwaite(comps) == pytest.approx(16)
    r = combine(comps)
    assert r.k == pytest.approx(2.120, abs=1e-3)  # t(0.975, 16)


def test_infinite_dof_gives_normal_k():
    assert coverage_factor(math.inf) == pytest.approx(1.960, abs=1e-3)


def test_unknown_distribution():
    with pytest.raises(ValueError):
        _ = Component("x", 1, "lognormal").standard_uncertainty


def test_propagate_matches_analytic_sensitivities():
    from labqc.uncertainty import propagate

    # y = a * b, so c_a = b and c_b = a
    y, r = propagate(
        lambda a, b: a * b,
        {"a": 2.0, "b": 5.0},
        {"a": Component("a", 0.1), "b": Component("b", 0.2)},
    )
    assert y == pytest.approx(10)
    assert r.combined == pytest.approx(math.hypot(5 * 0.1, 2 * 0.2), rel=1e-6)
