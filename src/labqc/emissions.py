"""Flue-gas emission conversions for combustion testing.

Concentrations from a gas analyser are usually in ppm (by volume) at the
measured oxygen level. Emission limits, for example in EN 303-5 for
solid-fuel boilers, are stated in mg/m3 of dry flue gas at standard
conditions (273.15 K, 101.325 kPa) and a reference oxygen level (10% O2 for
EN 303-5).
"""

from __future__ import annotations

from .uncertainty import Component, Result, propagate

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


def register_gas(name: str, molar_mass: float, overwrite: bool = False) -> None:
    """Add a gas to MOLAR_MASS (g/mol) so the ppm <-> mg/m3 conversions accept it.

    Refuses to change a gas already in the table unless overwrite=True.
    """
    if not name:
        raise ValueError("gas name must not be empty")
    if not molar_mass > 0:
        raise ValueError("molar mass must be positive")
    if name in MOLAR_MASS and not overwrite and MOLAR_MASS[name] != molar_mass:
        raise ValueError(f"{name} is already registered ({MOLAR_MASS[name]} g/mol)")
    MOLAR_MASS[name] = float(molar_mass)


def corrected_uncertainty(
    concentration: float,
    u_concentration: float,
    o2_measured: float,
    u_o2: float,
    o2_ref: float = 10.0,
    coverage: float = 0.95,
    k: float | None = None,
) -> tuple[float, Result]:
    """Uncertainty of a concentration corrected to reference O2 (GUM first order).

    Propagates the standard uncertainties of the measured concentration and
    of the measured O2 through to_reference_o2 with
    labqc.uncertainty.propagate. Returns (C_ref, Result); the Result table
    shows which of the two dominates. The O2 term grows quickly as O2_meas
    approaches 20.9 %, because the correction factor's denominator shrinks.
    """
    return propagate(
        lambda c, o2: to_reference_o2(c, o2, o2_ref),
        {"c": concentration, "o2": o2_measured},
        {
            "c": Component("Concentration", u_concentration),
            "o2": Component("Measured O2", u_o2),
        },
        coverage=coverage,
        k=k,
    )
