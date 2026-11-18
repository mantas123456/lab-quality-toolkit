# Quick start

## An uncertainty budget

```python
from labqc.uncertainty import Component, combine, type_a

budget = [
    type_a([10.02, 10.05, 9.98, 10.01, 10.03]),  # repeatability, 4 dof
    Component("Reference standard", 0.010, "normal", k=2),  # certificate, U at k = 2
    Component("Temperature effect", 0.004, "rectangular"),  # ±0.004 half-width
]
result = combine(budget, value=10.02)
print(result.summary(relative=True))  # u_c, v_eff, k, U and the relative values
print(result.table)  # which component dominates
```

For a measurement model, write it as a function and let `propagate` find the sensitivity
coefficients; `monte_carlo` checks the result when the model is non-linear:

```python
from labqc.uncertainty import Component, monte_carlo, propagate


def concentration(c_meas, recovery):
    return c_meas / recovery


values = {"c_meas": 12.0, "recovery": 0.60}
inputs = {"c_meas": Component("C_meas", 0.3), "recovery": Component("Recovery", 0.10)}
y, gum = propagate(concentration, values, inputs)
mc = monte_carlo(concentration, values, inputs, seed=1)
print(gum)
print(mc)
```

## Method validation

```python
from labqc.validation import linearity, lod_loq, trueness

cal = linearity([0, 1, 2, 3, 4, 5], [0.1, 2.0, 4.2, 5.9, 8.1, 9.9])
lod, loq = lod_loq(cal)
print(cal.slope, cal.r_squared, lod, loq)
print(trueness([50.4, 50.7, 49.1, 49.0, 51.1], crm_value=50, crm_u=0.2).passed)
```

## Proficiency testing and QC

```python
from labqc.control_charts import limits_from_data, westgard
from labqc.proficiency import classify, z_score

z = z_score(10.75, assigned=10.0, sigma_pt=0.3)
print(round(z, 2), classify(z))  # 2.5 questionable

limits = limits_from_data([50.1, 49.8, 50.3, 49.9, 50.2, 50.0, 49.7, 50.4])
print(westgard([50.2, 50.9, 49.0], limits))
```

## Emissions

```python
from labqc.emissions import ppm_to_mg_m3, to_reference_o2

co = to_reference_o2(ppm_to_mg_m3(310, "CO"), o2_measured=12.8, o2_ref=10)
print(f"{co:.1f} mg/m3 at 10 % O2")
```
