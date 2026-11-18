# Changelog

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
