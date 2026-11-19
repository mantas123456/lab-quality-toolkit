# Sources to check

Items the validation needs a person to confirm against the printed sources. No value below
was invented: cases whose numbers I could not stand behind were left out and are listed here
instead, and cases whose numbers are confirmed but whose citation details are not are marked.

## Cases still to add (no value used yet)

| Function | What is needed |
|---|---|
| `proficiency.robust_mean_sd` | A worked example of Algorithm A from ISO 13528 (Annex C) with its data and the robust mean and SD it reports. Until then this function has no reference case. |
| `uncertainty.combine` / `propagate` | GUM (JCGM 100:2008) Annex H.1, end-gauge calibration: the input estimates, standard uncertainties, degrees of freedom and the published u_c, v_eff and U. A multi-input published budget would strengthen the validation. |
| `validation.trueness` | A worked example from ERM Application Note 1 (bias against a CRM). The current pass/fail case is a hand calculation of its criterion. |
| `control_charts.ewma` | Montgomery's EWMA example on the CUSUM data (lambda = 0.1, L = 2.7): at which observation the book's chart first signals. labqc signals at observation 29 (EWMA 10.647 > UCL 10.619); the case was left out because I am not sure whether the book says 28 or 29. |
| `topdown.*` | The worked examples in Nordtest TR 537 (ed. 4, 2017), for example the ammonium-in-water example: control-sample SD, PT biases and u(Cref), and the published u(Rw), u(bias) and U. The current cases are hand calculations of the formulas. |
| `conformity.decide` | A numerical example from ILAC G8:09/2019 or JCGM 106:2012 (for example a probability of conformance worked in JCGM 106 Annex). The current cases follow the rule definitions and standard-normal table values. |
| `outliers.grubbs_two` | ISO 5725-2 Table 5, two largest / two smallest: the published critical values. labqc simulates them; at n = 10 it gives 0.187 / 0.114 (5 % / 1 %), and from memory the table says about 0.1864 / 0.1150. Confirm and add table cases. |
| `outliers.cochran` | ISO 5725-2 Table 4: critical values to add as cases. The F-distribution formula gives 0.602 / 0.717 for p = 10, n = 2; from memory the table says 0.602 / 0.718. |
| `comparison.*` | A published worked example of Passing-Bablok and Deming regression (for example from CLSI EP09 or the original papers) with slope, intercept and intervals. The current cases are hand calculations. |
| `equipment.drift` | The interval rule is labqc's own; if the laboratory follows ILAC-G24 / OIML D 10, cite the method used. |
| EN 14181 | labqc has no EN 14181 (QAL2/AST) functions, so there are no cases. |

## Citations to confirm (values already checked)

The numbers in these cases agree with the source data and results as I recall them, and the
calculation reproduces them, but the edition, section or clause should be confirmed and added.

| Case file | Detail to confirm |
|---|---|
| `validation.linearity.csv` | Miller & Miller: edition and section of the weighted regression example (absorbances 0.009 to 0.739 with SDs 0.001 to 0.022). |
| `validation.intermediate_precision.csv` | Miller & Miller: edition and section of the one-way ANOVA example (four conditions, three replicates; mean squares 62 and 3). |
| `validation.trueness.csv` | Miller & Miller: edition and section of the example comparing a mean with a known value (50.4, 50.7, 49.1, 49.0, 51.1 against 50; t = 0.14). |
| `control_charts.cusum.csv`, `control_charts.ewma.csv` | Montgomery: edition and example numbers of the tabular CUSUM and EWMA examples (30 observations, target 10, sigma 1). |
| `uncertainty.monte_carlo.csv` | JCGM 101:2008 9.2.2 and 9.2.3: table numbers for the additive-model intervals (±3.92 normal, ±3.88 rectangular). |
| `uncertainty.numerical_tolerance.csv`, `uncertainty.compare_with_monte_carlo.csv` | JCGM 101:2008 7.9.2 and 8.2: confirm that delta is taken from the Monte Carlo u(y) and the clause numbers. The values are hand calculations of the stated rule. |
| `conformity.*.csv` | ILAC G8:09/2019 section numbers for simple acceptance, guarded acceptance/rejection and non-binary statements; JCGM 106:2012 clause for the probability of conformance (cited as 7.2-7.3). |
| `outliers.grubbs_critical.csv` | ISO 5725-2 Table 5 edition and table number for the one-value Grubbs critical values (n = 4, 5, 10). |
| `validation.inverse_prediction.csv` | Miller & Miller: edition and section of the fluorescence calibration example (x0 = 0.72, 6.21, 11.13). |
| `uncertainty.standard_uncertainty.csv` | JCGM 101:2008 clause for the arcsine (U-shaped) distribution. |
| `proficiency.*.csv` | ISO 13528:2022 clause numbers for z, zeta, E_n and the action/warning signals (cited as 9.4, 9.6, 9.7, 9.4.2, 9.7.2). |
| `validation.intermediate_precision.csv` | ISO 5725-2 clause for s_r and s_L from the ANOVA mean squares (cited as 7.4). |
| `emissions.to_reference_o2.csv` | The standard to cite for the O2 reference correction (cited as EN 303-5 practice, with 20.9 % O2 in air). |
| `control_charts.westgard_levels.csv` | westgard.com reading of the across-runs forms of 4_1s, 10_x, 3_1s and 12_x for two and three control levels. |

When a value or citation is confirmed, edit the CSV in `validation/cases/` and run
`python validation/run_validation.py` to refresh `validation/report.md`.
