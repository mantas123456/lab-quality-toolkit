# Changelog

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
