"""Flue-gas emission conversions for combustion testing.

Concentrations from a gas analyser are usually in ppm (by volume) at the
measured oxygen level. Emission limits, for example in EN 303-5 for
solid-fuel boilers, are stated in mg/m3 of dry flue gas at standard
conditions (273.15 K, 101.325 kPa) and a reference oxygen level (10% O2 for
EN 303-5).
"""

from __future__ import annotations

O2_AIR = 20.9  # % O2 in dry air, as used in EN and ISO stack-emission standards
MOLAR_VOLUME_STP = 22.414  # L/mol at 273.15 K and 101.325 kPa

MOLAR_MASS = {  # g/mol
    "CO": 28.010,
    "NO": 30.006,
    "NO2": 46.006,  # NOx is conventionally reported as NO2
    "SO2": 64.066,
    "CO2": 44.009,
    "CH4": 16.043,
    "C3H8": 44.097,  # OGC is often reported as propane equivalent
}


def ppm_to_mg_m3(ppm: float, gas: str) -> float:
    """ppm by volume to mg/m3 at 273.15 K and 101.325 kPa."""
    return ppm * MOLAR_MASS[gas] / MOLAR_VOLUME_STP


def mg_m3_to_ppm(mg_m3: float, gas: str) -> float:
    return mg_m3 * MOLAR_VOLUME_STP / MOLAR_MASS[gas]


def to_reference_o2(concentration: float, o2_measured: float, o2_ref: float = 10.0) -> float:
    """Correct a dry concentration to a reference oxygen level.

    C_ref = C_meas * (20.9 - O2_ref) / (20.9 - O2_meas)
    """
    if not 0 <= o2_measured < O2_AIR:
        raise ValueError("measured O2 must be between 0 and 20.9 %")
    return concentration * (O2_AIR - o2_ref) / (O2_AIR - o2_measured)


def wet_to_dry(concentration_wet: float, water_vol_fraction: float) -> float:
    """Convert a wet-basis concentration to dry basis."""
    if not 0 <= water_vol_fraction < 1:
        raise ValueError("water fraction must be in [0, 1)")
    return concentration_wet / (1 - water_vol_fraction)


def to_temperature_pressure(concentration: float, t_c: float, p_kpa: float) -> float:
    """Convert mg/m3 measured at t_c (degC) and p_kpa to standard conditions."""
    return concentration * (273.15 + t_c) / 273.15 * 101.325 / p_kpa
