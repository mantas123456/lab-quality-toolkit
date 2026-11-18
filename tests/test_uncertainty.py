import math

import numpy as np
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


# --- v0.2: correlation -------------------------------------------------------


def test_full_positive_correlation_gives_linear_sum():
    # GUM 5.2.2 note 1: with r = 1 and positive c_i, u_c = sum(c_i * u_i)
    r = combine([Component("a", 3), Component("b", 4)], correlation={("a", "b"): 1.0})
    assert r.combined == pytest.approx(7)
    assert r.covariance == pytest.approx(2 * 3 * 4)


def test_full_negative_correlation_gives_difference():
    r = combine([Component("a", 3), Component("b", 4)], correlation={("b", "a"): -1.0})
    assert r.combined == pytest.approx(1)


def test_zero_correlation_matches_uncorrelated():
    comps = [Component("a", 3), Component("b", 4)]
    assert combine(comps, correlation={("a", "b"): 0.0}).combined == pytest.approx(5)


def test_correlated_weighings_cancel_in_a_difference():
    # y = m2 - m1 on one balance: a shared calibration offset (r = 1) cancels out
    from labqc.uncertainty import propagate

    inputs = {"m1": Component("Weighing m1", 0.001), "m2": Component("Weighing m2", 0.001)}
    y, r = propagate(
        lambda m1, m2: m2 - m1,
        {"m1": 10.0, "m2": 15.0},
        inputs,
        correlation={("m1", "m2"): 1.0},  # argument names
    )
    assert y == pytest.approx(5)
    assert r.combined == pytest.approx(0, abs=1e-9)
    # component names work too, and r = 0.5 gives u_c = u * sqrt(2 - 2 * 0.5) = u
    _, r = propagate(
        lambda m1, m2: m2 - m1,
        {"m1": 10.0, "m2": 15.0},
        inputs,
        correlation={("Weighing m1", "Weighing m2"): 0.5},
    )
    assert r.combined == pytest.approx(0.001, rel=1e-6)


@pytest.mark.parametrize(
    "correlation",
    [
        {("a", "b"): 1.2},  # outside [-1, 1]
        {("a", "b"): 0.5, ("b", "a"): 0.4},  # not symmetric
        {("a", "x"): 0.5},  # unknown component
        {("a", "a"): 0.9},  # self-correlation must be 1
        {("a", "b"): 0.9, ("b", "c"): 0.9, ("a", "c"): -0.9},  # not positive semi-definite
    ],
)
def test_invalid_correlation_raises(correlation):
    comps = [Component("a", 1), Component("b", 1), Component("c", 1)]
    with pytest.raises(ValueError):
        combine(comps, correlation=correlation)


# --- v0.2: relative uncertainty ----------------------------------------------


def test_relative_uncertainty_from_propagate():
    from labqc.uncertainty import propagate

    # y = a * b: relative uncertainties add in quadrature
    y, r = propagate(
        lambda a, b: a * b,
        {"a": 2.0, "b": 5.0},
        {"a": Component("a", 0.1), "b": Component("b", 0.2)},
        k=2,
    )
    expected = math.hypot(0.1 / 2, 0.2 / 5)
    assert r.value == pytest.approx(10)
    assert r.relative_combined == pytest.approx(expected, rel=1e-6)
    assert r.relative_expanded == pytest.approx(2 * expected, rel=1e-6)
    assert "u_c/|y|" in r.summary(relative=True)
    assert "u_c/|y|" not in str(r)


def test_relative_uncertainty_needs_a_value():
    r = combine([Component("a", 1)])
    with pytest.raises(ValueError):
        _ = r.relative_combined
    assert combine([Component("a", 1)], value=-4).relative_combined == pytest.approx(0.25)


# --- v0.2: Monte Carlo (GUM Supplement 1) ------------------------------------


def test_monte_carlo_agrees_with_propagate_for_linear_model():
    from labqc.uncertainty import monte_carlo, propagate

    def model(a, b, c):
        return a + 2 * b - c

    values = {"a": 1.0, "b": 3.0, "c": 0.5}
    inputs = {
        "a": Component("a", 0.10),
        "b": Component("b", 0.05, "rectangular"),
        "c": Component("c", 0.08, "triangular"),
    }
    y, gum = propagate(model, values, inputs)
    mc = monte_carlo(model, values, inputs, seed=1)
    assert mc.mean == pytest.approx(y, abs=0.01 * gum.combined)
    assert mc.standard_uncertainty == pytest.approx(gum.combined, rel=0.02)


def test_monte_carlo_seed_is_repeatable():
    from labqc.uncertainty import monte_carlo

    args = (lambda a: a**2, {"a": 1.0}, {"a": Component("a", 0.1, "u-shaped")})
    first = monte_carlo(*args, n=10_000, seed=42)
    again = monte_carlo(*args, n=10_000, seed=42)
    other = monte_carlo(*args, n=10_000, seed=43)
    assert np.array_equal(first.samples, again.samples)
    assert first.interval == again.interval
    assert not np.array_equal(first.samples, other.samples)


@pytest.mark.parametrize(
    ("distribution", "half_width", "expected_high"),
    [
        ("normal", 1.0, 3.92),  # JCGM 101:2008 9.2.2, normal inputs
        ("rectangular", math.sqrt(3), 3.88),  # JCGM 101:2008 9.2.3, rectangular inputs
    ],
)
def test_monte_carlo_reproduces_gum_s1_additive_model(distribution, half_width, expected_high):
    """JCGM 101:2008 9.2: Y = X1 + X2 + X3 + X4, each X_i with u = 1 around 0.

    u(y) = 2 in both cases; the shortest 95 % interval is [-3.92, 3.92] for normal
    inputs and [-3.88, 3.88] for rectangular inputs (Tables 2 and 3).
    """
    from labqc.uncertainty import monte_carlo

    names = ["x1", "x2", "x3", "x4"]
    mc = monte_carlo(
        lambda x1, x2, x3, x4: x1 + x2 + x3 + x4,
        dict.fromkeys(names, 0.0),
        {n: Component(n, half_width, distribution) for n in names},
        n=1_000_000,
        seed=7,
    )
    assert mc.standard_uncertainty == pytest.approx(2.0, rel=0.01)
    assert mc.mean == pytest.approx(0.0, abs=0.01)
    assert mc.high == pytest.approx(expected_high, abs=0.02)
    assert mc.low == pytest.approx(-expected_high, abs=0.02)


def test_monte_carlo_with_correlation_and_extra():
    from labqc.uncertainty import monte_carlo

    # y = a - b with r = 0.5 gives u = 1; extra adds an independent u = 1 -> sqrt(2)
    mc = monte_carlo(
        lambda a, b: a - b,
        {"a": 5.0, "b": 2.0},
        {"a": Component("a", 1.0), "b": Component("b", 1.0)},
        extra=[Component("repeatability", 1.0)],
        correlation={("a", "b"): 0.5},
        seed=3,
    )
    assert mc.mean == pytest.approx(3.0, abs=0.02)
    assert mc.standard_uncertainty == pytest.approx(math.sqrt(2), rel=0.02)


def test_monte_carlo_correlation_needs_normal_inputs():
    from labqc.uncertainty import monte_carlo

    with pytest.raises(ValueError):
        monte_carlo(
            lambda a, b: a + b,
            {"a": 0.0, "b": 0.0},
            {"a": Component("a", 1.0, "rectangular"), "b": Component("b", 1.0)},
            correlation={("a", "b"): 0.5},
            n=1000,
        )


def test_monte_carlo_falls_back_for_scalar_only_models():
    from labqc.uncertainty import monte_carlo

    # math.log does not accept arrays, so the model is evaluated sample by sample
    mc = monte_carlo(lambda x: math.log(x), {"x": 10.0}, {"x": Component("x", 0.1)}, n=2000, seed=0)
    assert mc.samples.shape == (2000,)
    assert mc.standard_uncertainty == pytest.approx(0.01, rel=0.05)
