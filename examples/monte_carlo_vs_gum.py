"""GUM first-order propagation compared with Monte Carlo (GUM Supplement 1), plus correlation.

Part 1, moisture (nearly linear model): the 95 % intervals agree. Monte Carlo's u is larger
    because JCGM 101 samples the 4-dof repeatability from a t-distribution, whose standard
    deviation is sqrt(4 / 2) = 1.41 times s / sqrt(n); the GUM method puts that same
    widening into k = 2.77 instead.
Part 2, recovery correction (non-linear model, uncertain denominator): C = C_meas / R with
    R = 0.60 and u(R) = 0.10. The linear method gives a symmetric interval; Monte Carlo
    shows the real distribution is skewed upwards, so the first-order U is misleading.
Part 3, correlated weighings: the three weighings in the moisture model share one balance
    calibration (u = 0.001 g) and have independent resolution terms (u = 0.000289 g), so
    r = u_cal^2 / (u_cal^2 + u_res^2) = 0.92. Part of the shared offset cancels.
"""

from moisture_uncertainty import inputs, moisture, repeat, values

from labqc.uncertainty import Component, monte_carlo, propagate

SEED = 2026


def compare(title, func, vals, inp, extra=(), correlation=None):
    y, gum = propagate(func, vals, inp, extra=extra, correlation=correlation)
    mc = monte_carlo(func, vals, inp, extra=extra, correlation=correlation, seed=SEED)
    print(title)
    print(
        f"  GUM (linear):  y = {y:.4g}, u = {gum.combined:.4g}, k = {gum.k:.2f}, "
        f"95 % interval [{y - gum.expanded:.4g}, {y + gum.expanded:.4g}]"
    )
    print(
        f"  Monte Carlo:   y = {mc.mean:.4g}, u = {mc.standard_uncertainty:.4g}, "
        f"95 % interval [{mc.low:.4g}, {mc.high:.4g}]"
    )
    return gum, mc


if __name__ == "__main__":
    compare("1. Moisture, M = (m2 - m3) / (m2 - m1) x 100 [%]", moisture, values, inputs, [repeat])

    print()
    compare(
        "2. Recovery-corrected result, C = C_meas / R [mg/kg]",
        lambda c_meas, recovery: c_meas / recovery,
        {"c_meas": 12.0, "recovery": 0.60},
        {"c_meas": Component("C_meas", 0.3), "recovery": Component("Recovery", 0.10)},
    )

    print()
    r = 0.001**2 / (0.001**2 + (0.0005 / 3**0.5) ** 2)
    pairs = {("m1", "m2"): r, ("m1", "m3"): r, ("m2", "m3"): r}
    _, independent = propagate(moisture, values, inputs)
    _, shared = propagate(moisture, values, inputs, correlation=pairs)
    print(f"3. Weighings only (no repeatability), r = {r:.2f} between weighings")
    print(f"  treated as independent: u = {independent.combined:.5f} %")
    print(
        f"  with shared calibration: u = {shared.combined:.5f} % "
        f"({shared.combined / independent.combined - 1:+.0%})"
    )
