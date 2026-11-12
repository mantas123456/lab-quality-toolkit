"""Convert analyser readings from a boiler test to mg/m3 at 10 % O2 (dry, 273 K, 1013 hPa).

Readings are averaged over the test period, as in an EN 303-5 type test. The limit
below is a placeholder: set it from the standard and boiler class you test against.
"""

from labqc.emissions import ppm_to_mg_m3, to_reference_o2

readings = {"CO": 310.0, "NO2": 118.0, "C3H8": 6.5}  # ppm, dry, mean of test period
o2_measured = 12.8  # % O2, dry
limit_mg_m3 = {"CO": 500.0}  # placeholder example limit

if __name__ == "__main__":
    print(
        f"Measured O2 {o2_measured} %, correction factor {(20.9 - 10) / (20.9 - o2_measured):.3f}\n"
    )
    for gas, ppm in readings.items():
        mg = to_reference_o2(ppm_to_mg_m3(ppm, gas), o2_measured, 10.0)
        line = f"{gas:5s} {ppm:7.1f} ppm  ->  {mg:7.1f} mg/m3 at 10 % O2"
        if gas in limit_mg_m3:
            line += f"   ({mg / limit_mg_m3[gas]:.0%} of example limit)"
        print(line)
