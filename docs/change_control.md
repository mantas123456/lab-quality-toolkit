# Change control

How a change to labqc is made, tested, validated and released, and what was re-validated in
each release. It follows the intent of ISO/IEC 17025 clause 7.11 (control of data and
information management): software used for results is validated before use, and changes are
authorised, documented and validated before they are introduced.

## How a change is made

1. **Issue.** Open a GitHub issue that says what changes and why (a bug, a new method, a
   standard revision). Note which functions are affected.
2. **Branch.** Work on a branch named after the issue, never directly on `main`.
3. **Tests first.** For a new or changed calculation, add the expected value to a unit test in
   `tests/` *before* changing the code, with its source in the test docstring. Add or update a
   reference case in `validation/cases/<module>.<function>.csv` with its source and working.
4. **Code.** Change the function, with a docstring that names the formula and the standard.
5. **Local checks.** All must pass:

   ```bash
   ruff check . && ruff format --check .
   pytest
   python validation/run_validation.py
   ```

6. **Pull request.** CI runs lint, the tests on Python 3.11 and 3.13, the examples and the
   validation job. A failed validation case blocks the merge.
7. **Review.** Read the diff and the refreshed `validation/report.md`: every expected value must
   trace to a source or a written working. labqc has one maintainer, so this is a documented
   self-review; a second reviewer is added when one is available.
8. **Release.** Update `CHANGELOG.md` and the version in `pyproject.toml` and
   `src/labqc/__init__.py`, commit the refreshed `validation/report.md`, merge, and push a tag
   `vX.Y.Z`. The release workflow runs the tests and the validation again, then publishes to
   PyPI. Nothing is published if any step fails.
9. **Record.** The release run keeps its `validation-report-vX.Y.Z` artifact for 90 days; it
   names the exact tagged commit. Download it and attach it to the GitHub release (or file it)
   as the validation record of that version. The `validation/report.md` committed before the
   tag is the copy that was reviewed; it names the commit before it.

Versions follow semantic versioning: a patch release fixes a result without changing the API,
a minor release adds functions, a major release changes existing behaviour.

**What is re-validated:** every release re-runs *all* reference cases, not only those of the
changed functions. The full run takes seconds, so there is no reason to select.

## Releases

| Version | Date | What changed | How it was tested and validated |
|---|---|---|---|
| 1.0.0 | unreleased | Validation suite (`validation/`), CI validation job, this change-control page | 91 reference cases across 32 functions, all passed; 97 unit and app tests |
| 0.6.0 | 2026-11-18 | Run records, JSON, Excel and PDF reports; Reports page in the app | 97 unit and app tests (71 library, 26 app). No formal validation suite yet. |
| 0.5.0 | 2026-11-18 | Streamlit web app; `correct_emission`, `components_from_table`, `predict_signal` | 85 tests (66 library, 19 app) |
| 0.4.0 | 2026-11-18 | Packaging for PyPI, documentation site, release workflow; first PyPI release | 58 tests |
| 0.3.0 | 2026-11-18 | Weighted regression, lack of fit, intermediate precision, trueness, PT history, multi-level Westgard, CUSUM, EWMA, emission uncertainty | 58 tests, including Miller & Miller and Montgomery worked examples |
| 0.2.0 | 2026-11-18 | Correlated inputs, Monte Carlo (GUM S1), relative uncertainty | 46 tests, including JCGM 101 9.2 |
| 0.1.0 | 2026-11-12 | First version: GUM budgets, validation basics, PT scores, Westgard rules, emissions | 28 tests against hand-calculated values |

Before 1.0.0, changes were checked by unit tests only; the reference-case validation started
with 1.0.0 and covers the functions of all earlier releases.

## Responsibility of the laboratory

The validation report shows that labqc computes what its documentation says, against
independent reference values. A laboratory that uses labqc for reported results must still
validate it for its own intended use (ISO/IEC 17025 7.11.2): check that the methods fit its
procedures, add its own reference cases if needed, and record the labqc version used for each
result (the `labqc.report` records do this).
