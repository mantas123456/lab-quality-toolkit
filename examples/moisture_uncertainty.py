"""Uncertainty budget for the moisture content of a wood-pellet sample by oven drying.

Model: M = (m2 - m3) / (m2 - m1) * 100   [% as received]
  m1  empty tray, m2  tray + sample before drying, m3  tray + sample after drying

Each weighing has a balance calibration uncertainty (certificate, U = 0.002 g, k = 2)
and a resolution term (0.001 g display, rectangular half-width 0.0005 g). Treating the
three weighings as uncorrelated is conservative: a shared calibration offset would
largely cancel in the differences. Repeatability comes from five replicate samples.
"""

from labqc.uncertainty import Component, propagate, type_a


def moisture(m1, m2, m3):
    return (m2 - m3) / (m2 - m1) * 100


def balance(name):
    # calibration and resolution combined for one weighing
    return Component(name, (0.001**2 + (0.0005 / 3**0.5) ** 2) ** 0.5)


values = {"m1": 120.512, "m2": 245.880, "m3": 237.140}
inputs = {k: balance(f"Weighing {k}") for k in values}
replicates = [6.97, 7.02, 6.94, 7.05, 6.99]  # % moisture, five test portions
repeat = type_a(replicates, "Repeatability (5 test portions)")

M, result = propagate(moisture, values, inputs, extra=[repeat])

if __name__ == "__main__":
    print(f"Moisture M = {M:.3f} %\n")
    print(result.table.to_string(index=False, float_format=lambda v: f"{v:.3g}"))
    print(f"\n{result}")
    print(f"\nReport: M = {M:.2f} % ± {result.expanded:.2f} % (k = {result.k:.2f}, 95 %)")
