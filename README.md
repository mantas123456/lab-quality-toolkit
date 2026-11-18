# labqc: laboratory quality calculations in Python

[![CI](https://github.com/mantas123456/lab-quality-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/mantas123456/lab-quality-toolkit/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/labqc)](https://pypi.org/project/labqc/)
[![Docs](https://img.shields.io/badge/docs-online-blue)](https://mantas123456.github.io/lab-quality-toolkit/)

The calculations an ISO/IEC 17025 laboratory does every week, usually in spreadsheets,
written as small, tested Python functions:

<!-- --8<-- [start:modules] -->
| Module | What it covers | Reference |
|---|---|---|
| `uncertainty` | GUM uncertainty budgets: Type A and B components, sensitivity coefficients (analytic or numerical), correlated inputs, Welch–Satterthwaite degrees of freedom, coverage factor, relative uncertainty; Monte Carlo propagation | JCGM 100:2008 (GUM), JCGM 101:2008 (GUM S1) |
| `validation` | Calibration linearity (ordinary or weighted) with confidence intervals and lack-of-fit test, LOD/LOQ, precision (RSD), intermediate precision by ANOVA, spike recovery, trueness against a CRM | ICH Q2, Eurachem guide, ERM Application Note 1 |
| `proficiency` | z, zeta and E<sub>n</sub> scores with interpretation; robust consensus mean (Algorithm A); z-score history across rounds | ISO 13528, ISO/IEC 17043 |
| `control_charts` | Shewhart limits; Westgard rules 1<sub>2s</sub>, 1<sub>3s</sub>, 2<sub>2s</sub>, R<sub>4s</sub>, 4<sub>1s</sub>, 10<sub>x</sub>, also across two or three control levels; CUSUM and EWMA charts | Westgard multirule QC; Montgomery, *Introduction to Statistical Quality Control* |
| `emissions` | ppm ↔ mg/m³ at standard conditions, correction to reference O₂ and its uncertainty, wet ↔ dry, user-defined gases | Stack-emission practice, e.g. EN 303-5 at 10 % O₂ |

Every function is tested against hand-calculated values or textbook worked examples (58 tests),
and the examples below run in CI.
<!-- --8<-- [end:modules] -->

<!-- --8<-- [start:examples] -->
## Example 1: uncertainty of a moisture determination

Oven-dry moisture of a wood-pellet sample, `M = (m2 − m3) / (m2 − m1) × 100`, with balance
calibration and resolution for each weighing plus repeatability from five test portions.
Sensitivity coefficients are found numerically from the model function
([`examples/moisture_uncertainty.py`](https://github.com/mantas123456/lab-quality-toolkit/blob/main/examples/moisture_uncertainty.py)).

```text
                      component     u_i    c_i  contribution  dof  share_of_variance
Repeatability (5 test portions)  0.0191      1        0.0191    4              0.996
                    Weighing m3 0.00104 -0.798       0.00083  inf            0.00188
                    Weighing m2 0.00104  0.742      0.000772  inf            0.00162
                    Weighing m1 0.00104 0.0556      5.79e-05  inf           9.12e-06

u_c = 0.01916, v_eff = 4.0, k = 2.77, U (95%) = 0.05306
Report: M = 6.97 % ± 0.05 % (k = 2.77, 95 %)
```

Over 99 % of the variance comes from sample repeatability. A better balance would change
nothing; more test portions would. With only four degrees of freedom the coverage factor is
2.77, not 2, which a fixed "k = 2" spreadsheet gets wrong.

## Example 2: Westgard rules on daily QC

Twenty baseline days set the limits. A +1.4 mg/kg shift is introduced from day 45
([`examples/westgard_iqc.py`](https://github.com/mantas123456/lab-quality-toolkit/blob/main/examples/westgard_iqc.py)).

![Levey-Jennings chart](https://raw.githubusercontent.com/mantas123456/lab-quality-toolkit/main/examples/westgard_chart.png)

```text
    value      z   status             rules
27  47.99 -2.817  warning              1_2s
45  52.49  4.385   reject        1_2s, 1_3s
47  52.09  3.745   reject        1_2s, 1_3s
48  51.50  2.798   reject        1_2s, 2_2s
50  53.00  5.206   reject  1_2s, 1_3s, 4_1s
```

Day 27 is a lone 1<sub>2s</sub> warning that needs no action. The shift is caught on its
first day, and the 2<sub>2s</sub> and 4<sub>1s</sub> rules confirm the error is systematic
(calibration), not random.

## Example 3: boiler test emissions at reference oxygen

```text
Measured O2 12.8 %, correction factor 1.346
CO      310.0 ppm  ->    521.3 mg/m3 at 10 % O2   (104% of example limit)
NO2     118.0 ppm  ->    325.9 mg/m3 at 10 % O2
C3H8      6.5 ppm  ->     17.2 mg/m3 at 10 % O2
```

At high excess air, a raw reading that looks comfortably low can exceed a limit once it is
corrected to 10 % O₂ ([`examples/boiler_emissions.py`](https://github.com/mantas123456/lab-quality-toolkit/blob/main/examples/boiler_emissions.py)).

## Example 4: Monte Carlo and correlated weighings

Version 0.2 adds Monte Carlo propagation (GUM Supplement 1) and correlated inputs
([`examples/monte_carlo_vs_gum.py`](https://github.com/mantas123456/lab-quality-toolkit/blob/main/examples/monte_carlo_vs_gum.py)).

```text
1. Moisture, M = (m2 - m3) / (m2 - m1) x 100 [%]
  GUM (linear):  y = 6.971, u = 0.01916, k = 2.77, 95 % interval [6.918, 7.025]
  Monte Carlo:   y = 6.971, u = 0.02704, 95 % interval [6.917, 7.024]

2. Recovery-corrected result, C = C_meas / R [mg/kg]
  GUM (linear):  y = 20, u = 3.371, k = 1.96, 95 % interval [13.39, 26.61]
  Monte Carlo:   y = 20.61, u = 3.843, 95 % interval [14.15, 28.12]

3. Weighings only (no repeatability), r = 0.92 between weighings
  treated as independent: u = 0.00114 %
  with shared calibration: u = 0.00031 % (-72%)
```

For the nearly linear moisture model the two 95 % intervals agree. Monte Carlo's u is larger
only because a 4-dof Type A input is sampled from a t-distribution; the GUM method puts the
same widening into k = 2.77. Dividing by an uncertain recovery (R = 0.60 ± 0.10) is
non-linear: the real distribution is skewed upwards, and the first-order interval is too low
at both ends. When the three weighings share one balance calibration, most of the offset
cancels, and the balance contribution falls by 72 %.

```python
from labqc.uncertainty import Component, monte_carlo, propagate

inputs = {"a": Component("a", 0.1), "b": Component("b", 0.1)}
y, r = propagate(lambda a, b: a - b, {"a": 5.0, "b": 2.0}, inputs, correlation={("a", "b"): 0.8})
print(r.summary(relative=True))  # u_c, k, U and u_c/|y|, U/|y|
print(monte_carlo(lambda a, b: a / b, {"a": 5.0, "b": 2.0}, inputs, seed=1))
```

## New in 0.3: lab methods

```python
import pandas as pd
from labqc.validation import intermediate_precision, linearity, trueness
from labqc.emissions import corrected_uncertainty

# weighted calibration with duplicate standards: lack-of-fit test included
cal = linearity(
    [1, 1, 2, 2, 5, 5, 10, 10], [0.11, 0.10, 0.21, 0.19, 0.52, 0.49, 1.08, 0.97], weights="1/x"
)
print(cal.lack_of_fit.p_value)  # 0.90: a straight line is adequate

# three days x three replicates: repeatability 0.100, intermediate precision 0.224
days = pd.DataFrame(
    {
        "day": [1, 1, 1, 2, 2, 2, 3, 3, 3],
        "value": [10.1, 10.3, 10.2, 10.6, 10.4, 10.5, 10.0, 10.2, 10.1],
    }
)
ip = intermediate_precision(days, "value", "day")

# five results on a CRM certified at 50 with u = 0.2
print(trueness([50.4, 50.7, 49.1, 49.0, 51.1], crm_value=50, crm_u=0.2).passed)  # True

# CO from Example 3 with u(C) = 8 mg/m3 and u(O2) = 0.2 %: 521 ± 34 mg/m3 (k = 2)
c_ref, r = corrected_uncertainty(387.4, 8, o2_measured=12.8, u_o2=0.2, k=2)
```

`pt_history()` reviews a lab's z-scores across PT rounds, and `westgard_levels()`, `cusum()`
and `ewma()` cover two- and three-level QC and small shifts that Westgard rules miss.
<!-- --8<-- [end:examples] -->

## Use it

```bash
pip install labqc
```

Full documentation, with the API reference for every module:
[mantas123456.github.io/lab-quality-toolkit](https://mantas123456.github.io/lab-quality-toolkit/).

```python
from labqc.uncertainty import Component, combine, type_a
from labqc.proficiency import z_score, classify

budget = [
    type_a([10.02, 10.05, 9.98, 10.01, 10.03]),
    Component("Reference standard", 0.010, "normal", k=2),
    Component("Temperature effect", 0.004, "rectangular"),
]
print(combine(budget))  # u_c, v_eff, k, U

z = z_score(10.75, assigned=10.0, sigma_pt=0.3)
print(round(z, 2), classify(z))  # 2.5 questionable
```

## Develop

```bash
pip install -e ".[dev]"
pytest
ruff check .

pip install -e ".[docs]"
mkdocs serve        # documentation at http://127.0.0.1:8000
```

Releases: push a tag `v*` (for example `v0.4.0`) that matches the version in
`pyproject.toml`; GitHub Actions builds the package and publishes it to PyPI.

## Scope and limits

- `propagate()` uses first-order sensitivity coefficients. For strongly non-linear models,
  use `monte_carlo()` (GUM Supplement 1) and compare.
- Monte Carlo handles correlation only between normal inputs with infinite degrees of
  freedom. Welch–Satterthwaite is applied as for independent inputs, even when correlations
  are given.
- Units are stored on each component but not checked.
- This is a calculation aid, not validated software for regulated use. Check results
  against your own procedures.

## How this was built

I designed the analysis and checked the results. I used Claude Code as
a coding assistant.

---
Mantas Valantinavičius · measurement scientist, 14 years in ISO/IEC 17025 testing ·
[github.com/mantas123456](https://github.com/mantas123456)
