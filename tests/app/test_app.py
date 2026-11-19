"""Streamlit AppTest checks for the web app: every page runs, shows the same numbers as
the worked examples in examples/, and turns bad input into a plain st.error message."""

import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PAGES = sorted((ROOT / "app" / "pages").glob("*.py"))


def page_file(name: str) -> Path:
    """A page by the name Streamlit shows (the file name without its number)."""
    return next(p for p in PAGES if p.stem.split("_", 1)[1] == name)


UNCERTAINTY = page_file("Uncertainty_budget")
VALIDATION = page_file("Method_validation")
PT = page_file("Proficiency_testing")
QC = page_file("QC_charts")
EMISSIONS = page_file("Emissions")
REPORTS = page_file("Reports")
CALC_PAGES = [p for p in PAGES if p != REPORTS]  # every page with a calculation
sys.path.insert(0, str(ROOT / "examples"))


def run(path: Path, **state) -> AppTest:
    at = AppTest.from_file(str(path), default_timeout=60)
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def metric(at: AppTest, label: str) -> str:
    return next(m.value for m in at.metric if m.label == label)


@pytest.mark.parametrize("path", [ROOT / "app" / "Home.py", *PAGES], ids=lambda p: p.stem)
def test_page_runs_without_errors(path):
    at = run(path)
    assert not at.exception
    assert not at.error


@pytest.mark.parametrize("path", CALC_PAGES, ids=lambda p: p.stem)
def test_load_example_button(path):
    at = run(path)
    at.button[0].click().run()
    assert not at.exception
    assert not at.error


def test_uncertainty_matches_moisture_example():
    import moisture_uncertainty as ex

    at = run(UNCERTAINTY)
    assert metric(at, "U (95%)") == f"{ex.result.expanded:.4g}"
    assert metric(at, "k") == f"{ex.result.k:.2f}"
    assert metric(at, "u_c") == f"{ex.result.combined:.4g}"


def test_qc_matches_westgard_example():
    import westgard_iqc as ex

    at = run(QC)
    counts = ex.table["status"].value_counts()
    assert metric(at, "Warnings") == str(counts["warning"])
    assert metric(at, "Rejects") == str(counts["reject"])
    assert metric(at, "Centre") == f"{ex.limits.centre:.4g}"


def test_emissions_matches_boiler_example():
    """examples/boiler_emissions.py: CO 310 ppm at 12.8 % O2 is 104 % of the example limit."""
    at = run(EMISSIONS)
    assert [w.value for w in at.warning] == ["CO: 104 % of the limit"]
    assert metric(at, "O₂ correction factor") == "1.346"


def test_bad_distribution_is_a_plain_error():
    table = pd.DataFrame(
        {"name": ["Balance"], "value": [0.1], "distribution": ["lognormal"], "k": [1.0]}
    )
    at = run(UNCERTAINTY, unc_table=table, unc_version=0, unc_y=1.0, unc_unit="g")
    assert not at.exception
    assert "Distribution must be normal, rectangular, triangular or u-shaped" in at.error[0].value


def test_bad_number_in_validation_is_a_plain_error():
    at = run(VALIDATION)
    at.text_area(key="val_replicates").input("50.1, 49.8, abc").run()
    assert not at.exception
    assert at.error[0].value == "Replicate results: 'abc' is not a number"


def test_zero_sigma_pt_is_a_plain_error():
    at = run(PT)
    at.number_input(key="pt_sigma_pt").set_value(0.0).run()
    assert not at.exception
    assert at.error[0].value == "σ_pt must be greater than 0"


def test_demo_data_is_up_to_date():
    """The CSVs and JSON in app/demo_data are what make_demo_data.py builds from examples/."""
    sys.path.insert(0, str(ROOT / "app" / "demo_data"))
    import make_demo_data

    tables, scalars = make_demo_data.build()
    demo = ROOT / "app" / "demo_data"
    for name, df in tables.items():
        on_disk = (demo / f"{name}.csv").read_text(encoding="utf-8")
        assert on_disk == make_demo_data.csv_text(df), f"{name}.csv is out of date"
    assert (demo / "examples.json").read_text(encoding="utf-8") == make_demo_data.json_text(scalars)


# --- v0.6: reports and records -------------------------------------------------------


def _button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


@pytest.mark.parametrize("path", CALC_PAGES, ids=lambda p: p.stem)
def test_add_to_report_makes_a_record(path):
    at = run(path)
    _button(at, "Add to report").click().run()
    assert not at.exception
    records = at.session_state["records"]
    assert len(records) == 1
    record = type(records[0]).from_json(records[0].to_json())  # survives a JSON round trip
    assert record.function.startswith("labqc.")


def test_reports_page_with_records_builds_downloads():
    from labqc.report import RunRecord

    at = run(UNCERTAINTY)
    _button(at, "Add to report").click().run()
    records = [*at.session_state["records"], RunRecord("labqc.proficiency", {"x": 1.0})]
    at = run(REPORTS, records=records, analyst="A. Analyst")
    assert not at.exception
    assert not at.error
    labels = [b.label for b in at.get("download_button") if b.label != "Save project"]
    assert labels == ["Excel workbook, all 2 record(s)", "PDF report", "JSON record"]


def test_saved_budget_reloads_into_the_uncertainty_page():
    """Start from Home as `streamlit run app/Home.py` does, so st.switch_page can resolve pages."""
    import moisture_uncertainty as ex

    from labqc.report import RunRecord

    at = run(UNCERTAINTY)
    _button(at, "Add to report").click().run()
    saved = at.session_state["records"][0].to_json()  # what the JSON download contains

    at = AppTest.from_file(str(ROOT / "app" / "Home.py"), default_timeout=60).run()
    at.session_state["report_loaded"] = RunRecord.from_json(saved)
    at.switch_page("pages/9_Reports.py").run()
    _button(at, "Open this budget in Uncertainty budget").click().run()
    assert not at.exception
    assert not at.error
    assert metric(at, "U (95%)") == f"{ex.result.expanded:.4g}"  # now on the Uncertainty page


# --- v1.1: deep links, new tabs, Monte Carlo check, "What this means" -------------------


def examples_registry() -> dict:
    from common import EXAMPLES  # tests/app/conftest.py puts app/ on the path

    return EXAMPLES


def run_example(name: str) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app" / examples_registry()[name][0]), default_timeout=60)
    at.query_params["example"] = name
    return at.run()


def explanations(at: AppTest) -> list[str]:
    return [m.value for m in at.markdown if m.value.startswith("**What this means**")]


EXAMPLE_NAMES = [
    "moisture", "moisture-shared-balance", "calibration", "outliers", "method-comparison",
    "pt-round", "pt-history",
    "westgard", "westgard-levels", "cusum", "ewma", "qc-overview", "boiler", "topdown", "decision",
    "decision-guarded", "equipment-drift",
]  # fmt: skip


def test_example_list_is_complete():
    assert list(examples_registry()) == EXAMPLE_NAMES


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_every_example_link_opens_its_page(name):
    at = run_example(name)
    assert not at.exception
    assert not at.error
    assert not [w for w in at.warning if "example" in w.value]
    assert at.session_state[f"_example_{examples_registry()[name][0]}"] == name
    assert explanations(at), "every example shows a 'What this means' box"


def test_unknown_example_is_a_friendly_warning():
    at = AppTest.from_file(str(UNCERTAINTY), default_timeout=60)
    at.query_params["example"] = "no-such-example"
    at.run()
    assert not at.exception
    assert not at.error
    assert "There is no example called 'no-such-example'" in at.warning[0].value
    assert metric(at, "k") == "2.77"  # the page still opens with its default example


def test_example_of_another_page_links_there():
    at = AppTest.from_file(str(UNCERTAINTY), default_timeout=60)
    at.query_params["example"] = "boiler"
    at.run()
    assert not at.exception
    assert "(Emissions?example=boiler)" in at.warning[0].value


def test_home_lists_every_example():
    at = AppTest.from_file(str(ROOT / "app" / "Home.py"), default_timeout=60).run()
    text = "\n".join(m.value for m in at.markdown)
    for name in EXAMPLE_NAMES:
        assert f"?example={name})" in text


def test_example_link_loads_once_so_edits_survive():
    at = run_example("moisture")
    at.number_input(key="unc_y").set_value(7.5).run()
    assert at.session_state["unc_y"] == 7.5  # the rerun did not reload the example


def test_qc_page_has_the_three_tabs():
    at = run(QC)
    assert [t.label for t in at.tabs] == ["Westgard", "CUSUM", "EWMA"]


def test_qc_cusum_and_ewma_match_the_library():
    import westgard_iqc as ex

    from labqc.control_charts import cusum, ewma

    cu = cusum(ex.routine, ex.limits.centre, ex.limits.sd)
    ew = ewma(ex.routine, ex.limits.centre, ex.limits.sd)
    at = run_example("cusum")
    assert metric(at, "Signals") == str(int(cu["signal"].sum()))
    assert metric(at, "Points outside") == str(int(ew["signal"].sum()))
    first = next(m.value for m in at.metric if m.label == "First signal (day)")
    assert first == str(21 + int(cu["signal"].to_numpy().argmax()))


def test_qc_two_levels_match_westgard_levels():
    from labqc.control_charts import limits_from_data, westgard_levels

    data = pd.read_csv(ROOT / "app" / "demo_data" / "qc_levels.csv")
    wide = data.pivot(index="day", columns="level", values="value")[["low", "high"]]
    lims = {lv: limits_from_data(wide[lv].to_numpy()[:20]) for lv in wide}
    table = westgard_levels({lv: wide[lv].to_numpy()[20:] for lv in wide}, lims)
    at = run_example("westgard-levels")
    assert metric(at, "Levels") == "2"
    assert metric(at, "Rejects") == str(int((table["status"] == "reject").sum()))


def test_qc_levels_need_limits_from_data():
    at = run_example("westgard-levels")
    at.radio(key="qc_mode").set_value("Enter centre and SD").run()
    assert not at.exception
    assert "choose 'From the first results'" in at.error[0].value


def test_pt_history_tab_matches_the_library():
    from labqc.proficiency import pt_history

    history = pt_history(pd.read_csv(ROOT / "app" / "demo_data" / "pt_history.csv"))
    at = run_example("pt-history")
    assert [t.label for t in at.tabs] == ["Scores and round", "PT history"]
    assert metric(at, "Rounds") == str(len(history))
    assert metric(at, "Rounds needing action") == str(int(history["action"].sum()))


def test_pt_history_add_to_report():
    at = run_example("pt-history")
    next(b for b in at.button if b.key == "pt_hist_report").click().run()
    assert not at.exception
    assert at.session_state["records"][-1].function == "labqc.proficiency.pt_history"


def test_correlated_budget_matches_combine():
    from labqc.uncertainty import combine, components_from_table

    names = ["Weighing m1", "Weighing m2", "Weighing m3"]
    r_shared = 0.001**2 / (0.001**2 + (0.0005 / 3**0.5) ** 2)  # examples/monte_carlo_vs_gum.py
    corr = {(a, b): r_shared for i, a in enumerate(names) for b in names[i + 1 :]}
    budget = pd.read_csv(ROOT / "app" / "demo_data" / "moisture_budget.csv")
    expected = combine(components_from_table(budget), correlation=corr)
    at = run_example("moisture-shared-balance")
    assert metric(at, "u_c") == f"{expected.combined:.4g}"
    assert expected.covariance < 0  # the shared offset partly cancels


def test_monte_carlo_check_on_the_uncertainty_page():
    at = run(UNCERTAINTY)
    next(b for b in at.button if b.label == "Check with Monte Carlo").click().run()
    assert not at.exception
    assert not at.error
    assert metric(at, "Agreement") in ("confirmed", "not confirmed")
    assert "Monte Carlo interval" in [m.label for m in at.metric]
    assert len(explanations(at)) == 3  # budget, Monte Carlo check, and the top-down tab


def test_correlated_budget_saved_and_reloaded_keeps_its_correlation():
    from labqc.report import budget_from_record

    at = run_example("moisture-shared-balance")
    next(b for b in at.button if b.label == "Add to report").click().run()
    _, info = budget_from_record(at.session_state["records"][0])
    assert info["correlation"] and len(info["correlation"]) == 3


# --- v1.2: decision rules and top-down uncertainty --------------------------------------

DECISION = page_file("Decision_rules")


def test_pages_are_in_menu_order():
    assert [p.stem.split("_", 1)[1] for p in PAGES] == [
        "Uncertainty_budget", "Method_validation", "Proficiency_testing", "QC_charts",
        "QC_overview", "Emissions", "Decision_rules", "Equipment_drift", "Reports",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("name", "outcome"), [("decision", "pass"), ("decision-guarded", "conditional pass")]
)
def test_decision_page_matches_decide(name, outcome):
    from common import examples

    from labqc.conformity import decide

    ex = examples()["decision"]
    rule = "simple" if name == "decision" else "non-binary"
    d = decide(ex["value"], ex["U"], upper=ex["upper"], rule=rule, k=ex["k"], unit=ex["unit"])
    at = run_example(name)
    assert metric(at, "Outcome") == outcome == d.outcome
    assert metric(at, "Probability of conformance") == f"{d.probability:.1%}"
    assert at.code[0].value == d.wording


def test_decision_bad_limits_are_a_plain_error():
    at = run(DECISION)
    at.checkbox(key="dec_has_lower").check().run()
    at.number_input(key="dec_lower").set_value(12.0).run()
    assert not at.exception
    assert at.error[0].value == "the lower limit must be below the upper limit"


def test_decision_without_limits_is_a_plain_error():
    at = run(DECISION)
    at.checkbox(key="dec_has_upper").uncheck().run()
    assert not at.exception
    assert at.error[0].value == "give a lower limit, an upper limit or both"


def _topdown_expected(source: str = "PT"):
    from common import examples

    from labqc.topdown import combine_topdown, u_bias_crm, u_bias_pt, u_rw

    demo = ROOT / "app" / "demo_data"
    qc = pd.read_csv(demo / "topdown_qc.csv")["value"]
    if source == "PT":
        pt = pd.read_csv(demo / "topdown_pt.csv")
        bias = u_bias_pt(pt["result"], pt["assigned"], pt["u_assigned"])
    else:
        crm = examples()["topdown_crm"]
        bias = u_bias_crm(crm["results"], crm["certified"], crm["u"])
    return combine_topdown(u_rw(qc), bias)


def test_topdown_tab_matches_the_library():
    expected = _topdown_expected()
    at = run_example("topdown")
    assert [t.label for t in at.tabs][:2] == ["GUM budget", "Top-down (Nordtest)"]
    assert metric(at, "u(Rw)") == f"{expected.u_rw:.3g}"
    assert metric(at, "u(bias)") == f"{expected.u_bias:.3g}"
    assert metric(at, "U (top-down, k = 2)") == f"{expected.expanded:.3g}"


def test_topdown_from_a_crm():
    expected = _topdown_expected("CRM")
    at = run_example("topdown")
    at.radio(key="td_source").set_value("CRM").run()
    assert not at.exception
    assert not at.error
    assert metric(at, "u(bias)") == f"{expected.u_bias:.3g}"


def test_topdown_relative_and_add_to_report():
    at = run_example("topdown")
    at.toggle(key="td_relative").set_value(True).run()
    assert not at.exception
    assert metric(at, "u(Rw)").endswith(" %")
    next(b for b in at.button if b.key == "td_report").click().run()
    record = at.session_state["records"][-1]
    assert record.function == "labqc.topdown.combine_topdown"
    assert record.settings["relative"] is True


# --- v1.3: QC overview, budget templates, project file -----------------------------------

OVERVIEW = page_file("QC_overview")


def test_qc_overview_matches_the_library():
    from labqc.control_charts import qc_overview

    expected = qc_overview(pd.read_csv(ROOT / "app" / "demo_data" / "qc_overview.csv"))
    at = run_example("qc-overview")
    counts = expected["status"].value_counts()
    assert metric(at, "Series") == str(len(expected))
    assert metric(at, "Rejects") == str(counts["reject"])
    labels = [b.label for b in at.button if b.key and b.key.startswith("qcov_")]
    assert len(labels) == len(expected)
    assert "🔴 reject (1_2s, 2_2s)" in labels


def test_qc_overview_cell_click_and_open_in_qc_charts():
    at = run(OVERVIEW)
    next(b for b in at.button if b.key == "qcov_Chloride (IC)_high").click().run()
    assert at.session_state["qcov_selected"] == ("Chloride (IC)", "high")
    assert "**Chloride (IC) / high**" in [m.value for m in at.markdown]
    next(b for b in at.button if b.label == "Open this series in QC charts").click().run()
    assert at.session_state["qc_mode"] == "Enter centre and SD"
    assert at.session_state["qc_centre"] == 200.0 and at.session_state["qc_sd"] == 4.0
    assert len(at.session_state["qc_table"]) == 30


@pytest.mark.parametrize("key", ["weighing", "dilution", "moisture", "o2"])
def test_budget_templates_load_and_match_combine(key):
    from common import examples

    from labqc.uncertainty import combine, components_from_table

    template = examples()["templates"][key]
    expected = combine(components_from_table(pd.DataFrame(template["rows"])))
    at = run(UNCERTAINTY)
    at.selectbox(key="unc_template").set_value(key).run()
    next(b for b in at.button if b.label == "Load template").click().run()
    assert not at.exception
    assert not at.error
    assert metric(at, "u_c") == f"{expected.combined:.4g}"
    assert any(template["title"] in c.value for c in at.caption)


def test_project_saved_on_one_run_reopens_in_a_new_session():
    import project

    at = run(UNCERTAINTY)
    at.number_input(key="unc_y").set_value(7.25).run()
    values, records = project.loads(project.dumps(at.session_state, "test"))
    assert values["unc_y"] == 7.25
    assert "unc_table" in values and "td_qc" in values

    fresh = AppTest.from_file(str(UNCERTAINTY), default_timeout=60)
    project.apply(fresh.session_state, values, records)
    fresh.run()
    assert not fresh.exception
    assert fresh.session_state["unc_y"] == 7.25
    assert metric(fresh, "Result").startswith("7.25")


def test_inputs_survive_a_visit_to_another_page():
    at = AppTest.from_file(str(ROOT / "app" / "Home.py"), default_timeout=60).run()
    at.switch_page("pages/7_Decision_rules.py").run()
    at.number_input(key="dec_value").set_value(9.9).run()
    at.switch_page("pages/9_Reports.py").run()
    at.switch_page("pages/7_Decision_rules.py").run()
    assert at.session_state["dec_value"] == 9.9


def test_save_project_button_in_the_sidebar():
    at = run(EMISSIONS)
    assert "Save project" in [b.label for b in at.get("download_button")]


# --- v1.4: outlier tests, method comparison, inverse prediction, equipment drift ----------

EQUIPMENT = page_file("Equipment_drift")


def test_validation_page_tabs():
    at = run(VALIDATION)
    assert [t.label for t in at.tabs] == [
        "Calibration and precision", "Outlier tests", "Method comparison",
    ]  # fmt: skip


def test_inverse_prediction_matches_the_library():
    from common import demo_table, examples

    from labqc.validation import inverse_prediction, linearity

    cal_data = demo_table("calibration")
    cal = linearity(cal_data["concentration"], cal_data["signal"])
    expected = inverse_prediction(cal, examples()["validation"]["sample_signals"])
    at = run_example("calibration")
    assert metric(at, "Sample concentration x0") == f"{expected.x0:.4g}"
    assert metric(at, "u(x0)") == f"{expected.u_x0:.3g}"


def test_outlier_tab_matches_the_library():
    from common import demo_table, examples

    from labqc.outliers import cochran, grubbs

    g1 = grubbs(examples()["outliers"]["values"])
    groups = demo_table("outliers_duplicates")
    ch = cochran(groups[["rep1", "rep2"]].to_numpy().tolist())
    at = run_example("outliers")
    assert metric(at, "Grubbs, one value: G") == f"{g1.statistic:.3f}"
    assert metric(at, "Cochran C") == f"{ch.statistic:.3f}"
    assert any("Lab 6" in m.value for m in at.markdown)
    next(b for b in at.button if b.key == "ol_report").click().run()
    assert at.session_state["records"][-1].function == "labqc.outliers"


def test_outlier_tab_bad_input_is_a_plain_error():
    at = run_example("outliers")
    at.text_area(key="ol_values").input("1, 2").run()
    assert not at.exception
    assert at.error[0].value == "the test needs at least 3 values"


def test_comparison_tab_matches_the_library():
    from common import demo_table

    from labqc.comparison import bland_altman, deming, passing_bablok

    data = demo_table("comparison")
    ba = bland_altman(data["old"], data["new"])
    pb = passing_bablok(data["old"], data["new"])
    at = run_example("method-comparison")
    assert metric(at, "Bias (y − x)") == f"{ba.bias:.3g}"
    assert metric(at, "Comparison slope") == f"{pb.slope:.4f}"
    at.radio(key="cmp_method").set_value("Deming").run()
    assert metric(at, "Comparison slope") == f"{deming(data['old'], data['new']).slope:.4f}"
    next(b for b in at.button if b.key == "cmp_report").click().run()
    assert at.session_state["records"][-1].settings["regression"] == "Deming"


def test_comparison_same_column_is_a_plain_error():
    at = run_example("method-comparison")
    at.selectbox(key="cmp_y").set_value("old").run()
    assert not at.exception
    assert at.error[0].value == "Choose two different columns for x and y"


def test_equipment_page_matches_the_library():
    from common import demo_table, examples

    from labqc.equipment import drift

    data = demo_table("equipment")
    d = drift(data["date"], data["error"], data["U"], examples()["equipment"]["tolerance"])
    at = run_example("equipment-drift")
    assert metric(at, "Drift per year") == f"{d.drift_per_year:+.3g} °C"
    assert metric(at, "Reaches the tolerance") == str(d.reach_date)
    assert any(d.suggestion in m.value for m in at.markdown)


def test_equipment_dates_out_of_order_are_a_plain_error():
    at = run(EQUIPMENT)
    at.number_input(key="eq_tolerance").set_value(0.0).run()
    assert not at.exception
    assert at.error[0].value == "the tolerance must be greater than 0"
