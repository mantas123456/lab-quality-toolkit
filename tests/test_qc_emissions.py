import pytest

from labqc.control_charts import Limits, limits_from_data, westgard
from labqc.emissions import mg_m3_to_ppm, ppm_to_mg_m3, to_reference_o2, wet_to_dry

L = Limits(100.0, 1.0)


def status(values):
    return westgard(values, L)


def test_in_control():
    assert (status([100, 101, 99, 100.5, 99.2])["status"] == "accept").all()


def test_1_2s_warning_and_1_3s_reject():
    t = status([100, 102.5, 100, 96.5])
    assert t.loc[1, "status"] == "warning"
    assert t.loc[3, "1_3s"] and t.loc[3, "status"] == "reject"


def test_2_2s_needs_same_side():
    assert status([102.2, 102.4])["2_2s"].iloc[-1]
    assert not status([102.2, 97.6])["2_2s"].iloc[-1]


def test_r_4s():
    assert status([102.3, 97.5])["R_4s"].iloc[-1]


def test_4_1s_and_10_x():
    assert status([101.2, 101.5, 101.1, 101.3])["4_1s"].iloc[-1]
    t = status([100.4] * 10)
    assert t["10_x"].iloc[-1] and not t["10_x"].iloc[-2]


def test_moving_range_limits():
    lim = limits_from_data([10, 12, 10, 12], method="moving_range")
    assert lim.centre == 11
    assert lim.sd == pytest.approx(2 / 1.128)


def test_ppm_conversion_round_trip():
    assert ppm_to_mg_m3(100, "CO") == pytest.approx(124.97, abs=0.01)
    assert mg_m3_to_ppm(ppm_to_mg_m3(42, "NO2"), "NO2") == pytest.approx(42)


def test_reference_oxygen():
    assert to_reference_o2(500, o2_measured=13, o2_ref=10) == pytest.approx(500 * 10.9 / 7.9)
    assert to_reference_o2(500, o2_measured=10, o2_ref=10) == pytest.approx(500)
    with pytest.raises(ValueError):
        to_reference_o2(500, o2_measured=21)


def test_wet_to_dry():
    assert wet_to_dry(90, 0.1) == pytest.approx(100)


# --- v0.3: multi-level Westgard, CUSUM, EWMA ---------------------------------

MONTGOMERY = [
    9.45, 7.99, 9.29, 11.66, 12.16, 10.18, 8.04, 11.46, 9.20, 10.34,
    9.03, 11.47, 10.51, 9.40, 10.08, 9.37, 10.62, 10.31, 8.52, 10.84,
    10.90, 9.33, 12.29, 11.50, 10.60, 11.08, 10.38, 11.62, 11.31, 10.52,
]  # fmt: skip


def _levels(low, high):
    from labqc.control_charts import westgard_levels

    return westgard_levels(
        {"low": low, "high": high}, {"low": Limits(10.0, 1.0), "high": Limits(50.0, 2.0)}
    )


def test_two_level_rules_across_materials():
    """Westgard et al., Clin. Chem. 27 (1981) 493, and westgard.com "Westgard Rules"
    for two control materials: 2_2s and R_4s within one run across levels, 4_1s over
    two runs x two levels, 10_x over five runs x two levels. Hand-built z-scores."""
    # run 0: both levels +2.2 SD -> 2_2s across levels
    t = _levels([12.2], [54.4])
    assert t.loc[0, "2_2s"] and t.loc[0, "status"] == "reject"
    # one level +2.5, the other -2.5 in the same run -> R_4s
    t = _levels([12.5], [45.0])
    assert t.loc[0, "R_4s"] and not t.loc[0, "2_2s"]
    # two runs x two levels at +1.5 SD -> 4_1s on run 1 only
    t = _levels([11.5, 11.5], [53.0, 53.0])
    assert t["4_1s"].tolist() == [False, True]
    # five runs x two levels slightly high -> 10_x on run 4
    t = _levels([10.3] * 5, [50.6] * 5)
    assert t["10_x"].tolist() == [False] * 4 + [True]
    assert t["status"].iloc[-1] == "reject"
    # one level in two consecutive runs beyond 2 SD -> 2_2s within material
    t = _levels([12.3, 12.4], [50.0, 50.0])
    assert t["2_2s"].tolist() == [False, True]
    # a lone 2.5 SD result is only a warning
    t = _levels([12.5], [50.0])
    assert t.loc[0, "status"] == "warning"


def test_three_level_rules():
    """westgard.com "Westgard Rules" for three control materials: 2of3_2s, 3_1s and 12_x."""
    from labqc.control_charts import westgard_levels

    lim = {n: Limits(0.0, 1.0) for n in ("a", "b", "c")}
    t = westgard_levels({"a": [2.3], "b": [2.1], "c": [0.0]}, lim)
    assert t.loc[0, "2of3_2s"] and t.loc[0, "status"] == "reject"
    t = westgard_levels({"a": [1.2], "b": [1.5], "c": [1.1]}, lim)
    assert t.loc[0, "3_1s"]
    t = westgard_levels({"a": [0.2] * 4, "b": [0.4] * 4, "c": [0.1] * 4}, lim)
    assert t["12_x"].tolist() == [False, False, False, True]
    with pytest.raises(ValueError):
        westgard_levels({"a": [0.0]}, {"a": Limits(0, 1)})


def test_cusum_montgomery_example():
    """Montgomery, Introduction to Statistical Quality Control, tabular CUSUM example
    (target 10, sigma 1, k = 0.5, h = 5; 20 in-control points then a 1 sigma shift):
    C+ first exceeds h at observation 29 with C+ = 5.28."""
    from labqc.control_charts import cusum

    c = cusum(MONTGOMERY, target=10, sd=1, k=0.5, h=5)
    first = int(c.index[c["signal"]][0])
    assert first == 28  # observation 29, zero-based index 28
    assert c.loc[28, "c_plus"] == pytest.approx(5.28, abs=0.005)
    assert c["signal_high"].iloc[28] and not c["signal_low"].any()


def test_ewma_montgomery_example():
    """Montgomery, EWMA example on the same data with lambda = 0.1, L = 2.7: the book's
    first values are z1 = 9.945 and UCL1 = 10.27. The limits widen towards
    10 + 2.7 sqrt(0.1 / 1.9) = 10.619; in this calculation the EWMA first crosses the
    UCL at observation 29 (EWMA 10.647)."""
    from labqc.control_charts import ewma

    e = ewma(MONTGOMERY, target=10, sd=1, lam=0.1, L=2.7)
    assert e.loc[0, "ewma"] == pytest.approx(9.945)
    assert e.loc[0, "ucl"] == pytest.approx(10.27, abs=0.005)
    assert e["ucl"].iloc[-1] == pytest.approx(10 + 2.7 * (0.1 / 1.9) ** 0.5, abs=1e-3)
    assert int(e.index[e["signal"]][0]) == 28
    assert e.loc[28, "ewma"] == pytest.approx(10.647, abs=1e-3)


# --- v0.3: emissions ------------------------------------------------------------


def test_register_gas(monkeypatch):
    """H2S molar mass from IUPAC standard atomic weights: 2 x 1.008 + 32.06 = 34.076 g/mol,
    so 100 ppm = 100 x 34.076 / 22.414 = 152.03 mg/m3 at 273.15 K, 101.325 kPa."""
    from labqc import emissions

    monkeypatch.setattr(emissions, "MOLAR_MASS", dict(emissions.MOLAR_MASS))
    emissions.register_gas("H2S", 34.076)
    assert ppm_to_mg_m3(100, "H2S") == pytest.approx(152.03, abs=0.01)
    with pytest.raises(ValueError):
        emissions.register_gas("CO", 30.0)  # would silently change CO
    emissions.register_gas("CO", 28.01, overwrite=True)
    with pytest.raises(ValueError):
        emissions.register_gas("X", 0)


def test_corrected_uncertainty_matches_analytic_derivatives():
    """GUM eq. (10) on C_ref = C (20.9 - O2_ref) / (20.9 - O2), by hand:
    dC_ref/dC = 10.9 / 7.9 and dC_ref/dO2 = C x 10.9 / 7.9^2 for C = 500, O2 = 13 %,
    O2_ref = 10 %; u(C) = 10 and u(O2) = 0.2 give u_c = sqrt(13.797^2 + 17.466^2) = 22.26 mg/m3."""
    from labqc.emissions import corrected_uncertainty

    c_ref, r = corrected_uncertainty(500, 10, o2_measured=13, u_o2=0.2, o2_ref=10, k=2)
    c1, c2 = 10.9 / 7.9, 500 * 10.9 / 7.9**2
    assert c_ref == pytest.approx(500 * 10.9 / 7.9)
    assert r.combined == pytest.approx(((c1 * 10) ** 2 + (c2 * 0.2) ** 2) ** 0.5, rel=1e-6)
    assert r.combined == pytest.approx(22.26, abs=0.01)
    assert r.expanded == pytest.approx(2 * r.combined)
    assert r.table.loc[0, "component"] == "Measured O2"  # the larger share here
