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
