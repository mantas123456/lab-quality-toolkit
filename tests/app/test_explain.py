"""The 'What this means' sentences (app/explain.py): short, factual, and right for each case."""

import math

import pandas as pd
import pytest

pytest.importorskip("streamlit")
import explain  # noqa: E402  (tests/app/conftest.py puts app/ on the path)


def budget(*shares):
    return pd.DataFrame(
        {"component": [f"c{i}" for i in range(len(shares))], "share_of_variance": shares}
    )


def test_uncertainty_dominant_component_and_small_dof():
    text = explain.uncertainty(budget(0.996, 0.002, 0.002), 2.77, 4.0, 0.0)
    assert text[0].startswith("c0 gives 99.60% of the variance. The next largest, c1, gives 0.2%")
    assert "k is 2.77, not 2" in text[1]


def test_uncertainty_shared_budget_and_infinite_dof():
    text = explain.uncertainty(budget(0.5, 0.3, 0.2), 1.96, math.inf, 0.0)
    assert text[0] == "c0 gives 50% of the variance. c1 follows with 30%."
    assert "infinite degrees of freedom" in text[1]


def test_uncertainty_mentions_correlation():
    text = explain.uncertainty(budget(1.0), 2.0, math.inf, -1e-6)
    assert "lower u_c" in text[1]


def test_monte_carlo_wording():
    assert "confirmed" in explain.monte_carlo(True, 0.001, 0.002, 0.005, 1, True)[0]
    no = explain.monte_carlo(False, 0.0013, 0.0009, 0.0005, 2, True)
    assert "not confirmed to 2 significant digits" in no[0]
    assert "t-distribution" in no[1]
    assert "shape" in explain.monte_carlo(False, 0.1, 0.1, 0.05, 2, False)[1]


def test_validation_wording():
    good = explain.validation(0.999, 0.42, False, 0.1, 0.3, 95.0)
    assert "no significant departure" in good[0]
    assert "95.0 %" in good[1]
    bad = explain.validation(0.99, 0.01, True, 0.1, 0.3, 95.0)
    assert "significant (p = 0.010)" in bad[0]
    assert "replicate standards" in explain.validation(0.99, None, None, 0.1, 0.3, 95.0)[0]


def test_pt_wording():
    text = explain.pt_scores(2.5, "questionable", 1.68, "unsatisfactory")
    assert text == [
        "z = 2.50 is questionable: your result is 2.50 σ_pt from the assigned value.",
        "|En| = 1.68 > 1: the difference is larger than the two expanded uncertainties allow.",
    ]
    round_table = pd.DataFrame(
        {"lab": ["A", "B", "C"], "status": ["satisfactory", "unsatisfactory", "unsatisfactory"]}
    )
    assert explain.pt_round(round_table, 10.0, 0.2)[1] == "B and C are unsatisfactory (|z| ≥ 3)."


def test_pt_history_wording():
    from labqc.proficiency import pt_history

    z = [0.3, -0.5, 2.4, -2.2, 0.1, 0.4, 0.8, 0.2, 1.1, 0.6, 0.3, 0.9, 0.5, -3.1]
    history = pt_history(pd.DataFrame({"date": [f"r{i:02d}" for i in range(14)], "z": z}))
    text = explain.pt_history(history)
    assert text[0].startswith("3 of the 14 rounds need action: r03 (two rounds in a row")
    assert "r12 (nine rounds on one side)" in text[0]
    assert "r13 (unsatisfactory)" in text[0]
    calm = pt_history(pd.DataFrame({"date": ["a", "b"], "z": [0.1, -0.2]}))
    assert explain.pt_history(calm)[0].startswith("None of the 2 rounds needs action")


RULES = ("1_2s", "1_3s", "2_2s", "R_4s", "4_1s", "10_x")


def status_table(values):
    from labqc.control_charts import Limits, westgard

    table = westgard(values, Limits(100, 1))
    table.insert(0, "day", range(1, len(values) + 1))
    return table


def test_westgard_wording():
    text = explain.westgard(status_table([100, 102.5, 103.5, 102.2]), "day", RULES)
    assert text[0] == "2 run(s) are rejected, the first at day 3 by 1_3s, 2_2s."
    assert text[1] == "2_2s points to systematic error, such as calibration; 1_3s to random error."
    assert explain.westgard(status_table([100, 102.5]), "day", RULES) == [
        "No run is rejected; 1 warning(s) need a check but no action."
    ]


def test_cusum_and_ewma_wording():
    from labqc.control_charts import cusum, ewma

    cu = cusum([10.0] * 5 + [9.0] * 15, 10.0, 1.0)
    cu.insert(0, "run", range(1, 21))
    assert "a downward shift" in explain.cusum(cu, "run", 5.0)[0]
    ew = ewma([10.0] * 5, 10.0, 1.0)
    ew.insert(0, "run", range(1, 6))
    assert "no drift" in explain.ewma(ew, "run", 0.2)[0]


def test_emissions_wording():
    table = pd.DataFrame(
        {"gas": ["CO", "NO2"], "% of limit": [104.2, 60.0], "result": ["FAIL", "pass"]}
    )
    text = explain.emissions(table, 1.346, 10.0)
    assert "diluted and are multiplied by 1.346" in text[0]
    assert text[1] == "Above the limit after correction: CO (104 %)."


def test_decision_wording():
    text = explain.decision("pass", "simple", 0.857, 0.0)
    assert (
        text[0]
        == "Under simple acceptance the result passes: it lies inside the acceptance limits."
    )
    assert "85.7%" in text[1] and "can be wrong" in text[1]
    sure = explain.decision("pass", "simple", 0.999, 0.0)
    assert "can be wrong" not in sure[1]
    assert (
        "no decision can be stated" in explain.decision("no clear decision", "guarded", 0.6, 1.5)[0]
    )


def test_topdown_wording():
    table = pd.DataFrame({"term": ["u(Rw)", "bias"], "share_of_variance": [0.24, 0.76]})
    text = explain.topdown(table, False, 2.6, 2.0, "PT")
    assert text[0].startswith("The bias terms give 76% of u_c²")
    assert text[1].startswith("U = 2.6 (k = 2)")
    table["share_of_variance"] = [0.8, 0.2]
    assert (
        "Within-lab reproducibility gives 80%" in explain.topdown(table, True, 5.1, 2.0, "CRM")[0]
    )


def test_outlier_wording():
    from labqc.outliers import cochran, grubbs, grubbs_two

    values = [25.3, 25.1, 25.4, 25.2, 25.0, 25.3, 25.2, 26.4, 25.1, 25.3]
    ch = cochran([[1, 1.1], [2, 2.1], [3, 3.05], [4, 4.1]])
    text = explain.outliers(grubbs(values), grubbs_two(values), ch, "Lab 3")
    assert text[0].startswith("26.4 is an outlier by the one-value Grubbs test")
    assert "technical reason" in text[1]
    calm = [10.0, 10.1, 9.9, 10.05, 9.95]
    assert explain.outliers(grubbs(calm), grubbs_two(calm), ch, "x")[0].startswith(
        "Neither Grubbs test"
    )


def test_comparison_wording():
    from labqc.comparison import bland_altman, passing_bablok

    x = [float(v) for v in range(1, 21)]
    y = [1.05 * v for v in x]
    text = explain.comparison(bland_altman(x, y), passing_bablok(x, y), "Passing-Bablok")
    assert "reads" in text[0] and "higher" in text[0]
    assert "excludes 1" in text[1] and "5.0%" in text[1]


def test_drift_wording():
    from labqc.equipment import drift

    d = drift(["2000-01-01", "2004-01-01"], [0.10, 0.18], U=0.05, tolerance=0.3)
    text = explain.drift(d, "°C")
    assert text[0].startswith("The error changes by +0.02 °C per year.")
    assert "02 Jul 2007" in text[0]
    assert text[1].startswith("Suggestion: shorten the interval (3.5 years).")
