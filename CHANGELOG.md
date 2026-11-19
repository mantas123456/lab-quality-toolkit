# Changelog

## 1.4.0 – more lab methods

### Added
- `labqc.outliers` (ISO 5725-2): `grubbs` (one value), `grubbs_two` (two values, either
  end), `cochran` (largest variance), each with critical values at 5 % and 1 % and a label
  ok / straggler / outlier. Grubbs single and Cochran critical values come from the t and F
  distributions; the two-value Grubbs critical values are simulated (fixed seed).
- `labqc.comparison`: `bland_altman` (bias, limits of agreement and their confidence
  intervals), `deming` (error ratio, jackknife intervals), `passing_bablok` (rank-based
  intervals and the cusum linearity test); `Line.agrees` checks consistency with y = x.
- `labqc.validation.inverse_prediction`: a sample's concentration and its standard
  uncertainty from m replicate readings on an unweighted line; `Linearity` now keeps the
  standards (`x`, `y`).
- `labqc.equipment.drift`: drift per year from successive certificates, when |error| + U is
  predicted to reach the tolerance, and a stated rule to shorten, keep or lengthen the
  calibration interval.
- 27 validation cases: Grubbs critical values from ISO 5725-2 Table 5, the Miller & Miller
  calibration example for inverse prediction, and hand calculations; table comparisons still
  to confirm are in `validation/TO_CHECK.md`.
- Web app: tabs *Outlier tests* and *Method comparison* on the Method validation page, a
  sample read back from the calibration line, and an *Equipment drift* page. Example links
  `outliers`, `method-comparison`, `equipment-drift`. The project file keeps their inputs.
- Docs pages for the three modules, linked to handbook chapters 7.2 and 6.4.

### Changed
- The Reports page file is `app/pages/9_Reports.py` (its address is unchanged).
- Version 1.4.0. No new dependencies.

## 1.3.0 – browser version, QC overview, templates, project file

### Added
- Browser version of the app: `web/build.py` writes a static stlite site (Streamlit on
  Pyodide, stlite 1.12.0 with Streamlit 1.65 and Python 3.14) that loads the same `app/`
  pages and installs labqc from the wheel; the docs workflow builds the wheel and publishes
  it on GitHub Pages under `/app/`. PDF reports are hidden there (no reportlab); Excel and
  JSON work. The Streamlit Cloud app is unchanged.
- `labqc.control_charts.qc_overview(data, baseline, method)`: the Westgard status of the
  latest run for every method and control level, with the rules broken and the limits used.
- *QC overview* page: one CSV (date, method, level, value, optional target and sd) as a grid
  coloured accept / warning / reject; a cell shows its chart and opens the series in QC
  charts. Example link `?example=qc-overview`.
- Budget templates on the Uncertainty page: weighing on a balance, volumetric dilution,
  oven-dry moisture, O₂ reference correction. Each row has a *source* column saying where the
  number usually comes from; sensitivity coefficients come from `propagate`.
- Project files: *Save project* / *Open a project* in the sidebar of every page; one
  versioned `.labqc.json` with every page's inputs (edits included) and the report records,
  checked before loading (`app/project.py`). Inputs now survive moving between pages.
- Tests: QC overview, templates, project round trip and schema check, inputs across pages,
  the browser build; a Playwright smoke test for the browser build that runs when
  `LABQC_WEB_URL` is set (228 tests).

### Changed
- Pages renumbered for the menu order (QC overview after QC charts); page addresses are
  unchanged. Example links are relative, so they work on both hosts.
- On Streamlit versions without `st.tabs(default=...)`, deep links open the first tab.
- Version 1.3.0.

## 1.2.0 – decision rules and top-down uncertainty

### Added
- `labqc.conformity`: `decide(value, U, lower, upper, rule, guard_band, k, unit)` → `Decision`
  with the outcome (pass, fail, conditional pass, conditional fail, no clear decision), the
  acceptance and rejection limits, the probability of conformance and suggested report
  wording; rules `simple`, `guarded` and `non-binary` (ILAC G8:09/2019);
  `probability_of_conformance` (JCGM 106, normal or t); `guard_band(U, r)`.
- `labqc.topdown` (Nordtest TR 537): `u_rw` from a control series (optionally with s_r from
  duplicates, `s_r_duplicates`), `u_bias_pt` from PT rounds, `u_bias_crm` from a CRM, and
  `combine_topdown` → `TopDownResult` with u_c, U = k u_c and a share-of-variance table;
  absolute or relative (%).
- 32 validation cases (hand calculations and standard-table values); the Nordtest worked
  examples are listed in `validation/TO_CHECK.md` to add from the printed report.
- Web app: a *Decision rules* page (decision, probability, a picture of the result with its
  interval against the limits and guard bands, report wording) and a *Top-down* tab on the
  Uncertainty page (QC CSV, optional duplicates, PT rounds or CRM). Example links
  `?example=decision`, `decision-guarded` and `topdown`.
- Docs pages for both modules, linked to the handbook chapters 7.8 and 7.6.

### Changed
- The Reports page file is now `app/pages/7_Reports.py`, after Decision rules (its address,
  `/Reports`, is unchanged).
- Version 1.2.0.

## 1.1.0 – the whole library in the app

### Added
- `labqc.uncertainty.monte_carlo_budget(components, value, correlation, ...)`: Monte Carlo
  (JCGM 101) for a budget given as components, the model a budget table stands for.
- `labqc.uncertainty.compare_with_monte_carlo(y, result, mc, n_dig=2)` → `Agreement`: checks a
  GUM interval against a Monte Carlo interval (JCGM 101 clause 8), with
  `numerical_tolerance(u, n_dig)` (JCGM 101 7.9.2). 13 new validation cases.
- `record_budget(..., correlation=)` stores correlations; `budget_from_record` returns them.
- Web app:
  - Deep links: `?example=<name>` opens a page with that example loaded (moisture,
    moisture-shared-balance, calibration, pt-round, pt-history, westgard, westgard-levels,
    cusum, ewma, boiler). The Home page lists them; unknown names show a warning.
  - QC charts: tabs for Westgard, CUSUM and EWMA; Westgard across two or three control levels
    from a CSV with a `level` column (`westgard_levels`).
  - Proficiency testing: a *PT history* tab (`pt_history`) with a z-score chart over rounds and
    the warning signals marked.
  - Uncertainty budget: an optional table of correlated inputs, and *Check with Monte Carlo*,
    which shows the Monte Carlo interval next to the GUM one and whether they agree.
  - A *What this means* box under each main result: two plain sentences read from the result
    (`app/explain.py`), with no calculation of their own.
- Tests: an AppTest for every `?example=` link and new tab; unit tests for the explanations
  (144 tests in all).

### Changed
- Classifier `Development Status :: 5 - Production/Stable`.
- The app needs Streamlit 1.67 or later (tabs that open on a chosen tab).
- Version 1.1.0.

## 1.0.0 – validated release

### Added
- `validation/`: 91 reference cases for 32 functions in one CSV per function (inputs,
  reference value, tolerance, source type, source and working), and `run_validation.py`, which
  runs them and writes `validation/report.md` (expected, got, tolerance, pass/fail, labqc and
  Python versions, git commit, date). Functions without a reference case are listed in the
  report; open source questions are in `validation/TO_CHECK.md`.
- CI job `validation` fails on any failed case and keeps the report as an artifact; the release
  workflow runs the validation before publishing.
- Documentation: Validation report page and a Change control page (process and release table).

### Changed
- Version 1.0.0. The README "Scope and limits" now points to the validation and to the
  laboratory's own validation for its intended use.

## 0.6.0 – reports and records

### Added
- `labqc.report`: `RunRecord` (function, inputs, settings, result, method, title, analyst,
  labqc version, UTC timestamp) with `to_json` / `from_json`; strict JSON, with infinite
  degrees of freedom stored as "inf". `record_budget()` and `budget_from_record()` save and
  reload uncertainty budgets.
- `to_excel(records, path)`, one sheet per record, and `to_pdf(record, path)`, a one-page report
  with title, meta data, method, inputs, settings and result. Both accept a path or a binary
  file object. `reportlab` and `openpyxl` are in the new `[reports]` extra.
- Web app: an *Add to report* button on every page; the Reports page lists the session's
  records, sets the analyst, downloads one Excel workbook, a PDF or a JSON record per result,
  and reloads a saved budget into the Uncertainty page.
- Tests: JSON round trip is identical, a reloaded budget gives the same U, PDF and Excel files
  are created; app tests for *Add to report*, the downloads and reloading a budget.

### Changed
- `labqc.__version__` is set before the submodules are imported, so they can record it.
- CI installs the `[reports]` extra; `app/requirements.txt` lists reportlab and openpyxl.

## 0.5.0 – web app

### Added
- Streamlit web app in `app/` (`streamlit run app/Home.py`): Home, Uncertainty budget, Method
  validation, Proficiency testing, QC charts, Emissions and a Reports placeholder. Inputs in
  the middle, results on the right, CSV export at the bottom, plotly charts, a "Load example
  data" button on every page and plain error messages instead of tracebacks.
- Demo data in `app/demo_data/`, generated from the scripts in `examples/` by
  `make_demo_data.py`, so the app shows the same numbers as the worked examples.
- `[app]` extra and `app/requirements.txt` (for Streamlit Community Cloud).
- App tests in `tests/app/` with Streamlit's AppTest, run in CI: every page runs, matches the
  examples, and shows bad input as an error message.
- Library functions the app needed, each with a test: `uncertainty.components_from_table()`,
  `Linearity.predict_signal()`, `emissions.correct_emission()` (unit, wet/dry, temperature and
  pressure, reference O₂ and % of limit in one call) and `emissions.percent_of_limit()`.

### Changed
- An unknown distribution now raises "Distribution must be normal, rectangular, triangular or
  u-shaped, not '…'".
- CI installs the `[app]` extra.

## 0.4.0 – publish

### Added
- Ready for PyPI: full package metadata (SPDX licence, classifiers, project URLs, keywords),
  `py.typed` marker for type checkers, README links that work on PyPI.
- Documentation site with MkDocs Material and mkdocstrings: Home, Install, Quick start, an API
  page per module generated from the docstrings, Worked examples and this changelog.
  `pip install -e ".[docs]"` and `mkdocs serve` to build it locally.
- `.github/workflows/docs.yml` builds the site (strict) and deploys it to GitHub Pages on every
  push to main.
- `.github/workflows/release.yml` runs the tests, builds the sdist and wheel, checks them with
  twine and publishes to PyPI by trusted publishing when a tag `v*` is pushed. The tag must
  match the version in `pyproject.toml`.

### Changed
- CI uses `actions/checkout@v5` and `actions/setup-python@v6` (Node 24).
- `build` and `twine` added to the `dev` extra.

## 0.3.0 – fuller lab methods

### Added
- `validation`: weighted calibration lines (`weights="1/x"`, `"1/x^2"` or explicit weights
  such as 1/s²); `lack_of_fit()` F-test from replicate standards, also reported in
  `Linearity.lack_of_fit`; `Linearity.weighted_residuals`; `intermediate_precision()` by
  one-way ANOVA (repeatability, between-group and intermediate SD); `trueness()` against a
  CRM with bias, one-sample t-test and the ERM Application Note 1 pass/fail criterion.
- `proficiency`: `pt_history()` reviews z-scores across rounds and flags two |z| > 2 in a row
  and nine rounds on one side of zero.
- `control_charts`: `westgard_levels()` for two or three control materials per run
  (2_2s, 2of3_2s, R_4s, 4_1s, 3_1s, 10_x, 12_x across levels and runs); tabular `cusum()`;
  `ewma()` with exact limits.
- `emissions`: `register_gas()` for gases not in the built-in table;
  `corrected_uncertainty()` propagates u(C) and u(O₂) through the reference-O₂ correction.
- Tests reproduce textbook worked examples: Miller & Miller (weighted regression, one-way
  ANOVA, t-test against a known value) and Montgomery (tabular CUSUM, EWMA).

### Changed
- `linearity()` now fits with its own weighted least-squares code instead of
  `scipy.stats.linregress`; unweighted results are unchanged.

## 0.2.0 – better uncertainty

### Added
- Correlated inputs: `combine()` and `propagate()` take `correlation={("a", "b"): r}` and add
  the covariance terms 2·c_i·c_j·u_i·u_j·r_ij to u_c² (GUM 5.2.2). The matrix is checked:
  coefficients in [−1, 1], one value per pair, positive semi-definite. In `propagate()` the
  keys can be argument names or component names. `Result.covariance` holds the covariance part
  of u_c².
- `correlation_matrix()` to build and check a correlation matrix on its own.
- Monte Carlo propagation, `monte_carlo()`, following GUM Supplement 1 (JCGM 101:2008): normal
  (Student t when dof is finite), rectangular, triangular and u-shaped inputs; correlated
  normal inputs; mean, u(y), shortest coverage interval and the samples; `seed` for repeatable
  results.
- Relative uncertainty: `Result.value`, `relative_combined` (u_c/|y|), `relative_expanded`
  (U/|y|) and `summary(relative=True)`. `propagate()` fills `value`; `combine()` takes `value=`.
- Example `examples/monte_carlo_vs_gum.py`, run in CI.
- Tests reproduce the JCGM 101:2008 9.2 additive-model intervals (±3.92 for normal inputs,
  ±3.88 for rectangular inputs).

### Changed
- With correlations, `share_of_variance` no longer sums to 1; the remainder is
  `Result.covariance`. Uncorrelated budgets give the same numbers as 0.1.0.

## 0.1.0

First release: GUM uncertainty budgets, method validation, proficiency-test scores, Westgard
rules and flue-gas emission conversions.
