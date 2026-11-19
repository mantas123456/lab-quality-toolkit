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


@pytest.mark.parametrize("path", PAGES[:5], ids=lambda p: p.stem)
def test_load_example_button(path):
    at = run(path)
    at.button[0].click().run()
    assert not at.exception
    assert not at.error


def test_uncertainty_matches_moisture_example():
    import moisture_uncertainty as ex

    at = run(PAGES[0])
    assert metric(at, "U (95%)") == f"{ex.result.expanded:.4g}"
    assert metric(at, "k") == f"{ex.result.k:.2f}"
    assert metric(at, "u_c") == f"{ex.result.combined:.4g}"


def test_qc_matches_westgard_example():
    import westgard_iqc as ex

    at = run(PAGES[3])
    counts = ex.table["status"].value_counts()
    assert metric(at, "Warnings") == str(counts["warning"])
    assert metric(at, "Rejects") == str(counts["reject"])
    assert metric(at, "Centre") == f"{ex.limits.centre:.4g}"


def test_emissions_matches_boiler_example():
    """examples/boiler_emissions.py: CO 310 ppm at 12.8 % O2 is 104 % of the example limit."""
    at = run(PAGES[4])
    assert [w.value for w in at.warning] == ["CO: 104 % of the limit"]
    assert metric(at, "O₂ correction factor") == "1.346"


def test_bad_distribution_is_a_plain_error():
    table = pd.DataFrame(
        {"name": ["Balance"], "value": [0.1], "distribution": ["lognormal"], "k": [1.0]}
    )
    at = run(PAGES[0], unc_table=table, unc_version=0, unc_y=1.0, unc_unit="g")
    assert not at.exception
    assert "Distribution must be normal, rectangular, triangular or u-shaped" in at.error[0].value


def test_bad_number_in_validation_is_a_plain_error():
    at = run(PAGES[1])
    at.text_area(key="val_replicates").input("50.1, 49.8, abc").run()
    assert not at.exception
    assert at.error[0].value == "Replicate results: 'abc' is not a number"


def test_zero_sigma_pt_is_a_plain_error():
    at = run(PAGES[2])
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


@pytest.mark.parametrize("path", PAGES[:5], ids=lambda p: p.stem)
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

    at = run(PAGES[0])
    _button(at, "Add to report").click().run()
    records = [*at.session_state["records"], RunRecord("labqc.proficiency", {"x": 1.0})]
    at = run(PAGES[5], records=records, analyst="A. Analyst")
    assert not at.exception
    assert not at.error
    labels = [b.label for b in at.get("download_button")]
    assert labels == ["Excel workbook, all 2 record(s)", "PDF report", "JSON record"]


def test_saved_budget_reloads_into_the_uncertainty_page():
    """Start from Home as `streamlit run app/Home.py` does, so st.switch_page can resolve pages."""
    import moisture_uncertainty as ex

    from labqc.report import RunRecord

    at = run(PAGES[0])
    _button(at, "Add to report").click().run()
    saved = at.session_state["records"][0].to_json()  # what the JSON download contains

    at = AppTest.from_file(str(ROOT / "app" / "Home.py"), default_timeout=60).run()
    at.session_state["report_loaded"] = RunRecord.from_json(saved)
    at.switch_page("pages/6_Reports.py").run()
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
    "moisture", "moisture-shared-balance", "calibration", "pt-round", "pt-history",
    "westgard", "westgard-levels", "cusum", "ewma", "boiler",
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
    at = AppTest.from_file(str(PAGES[0]), default_timeout=60)
    at.query_params["example"] = "no-such-example"
    at.run()
    assert not at.exception
    assert not at.error
    assert "There is no example called 'no-such-example'" in at.warning[0].value
    assert metric(at, "k") == "2.77"  # the page still opens with its default example


def test_example_of_another_page_links_there():
    at = AppTest.from_file(str(PAGES[0]), default_timeout=60)
    at.query_params["example"] = "boiler"
    at.run()
    assert not at.exception
    assert "(/Emissions?example=boiler)" in at.warning[0].value


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
    at = run(PAGES[3])
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
    at = run(PAGES[0])
    next(b for b in at.button if b.label == "Check with Monte Carlo").click().run()
    assert not at.exception
    assert not at.error
    assert metric(at, "Agreement") in ("confirmed", "not confirmed")
    assert "Monte Carlo interval" in [m.label for m in at.metric]
    assert len(explanations(at)) == 2  # the budget's and the Monte Carlo check's


def test_correlated_budget_saved_and_reloaded_keeps_its_correlation():
    from labqc.report import budget_from_record

    at = run_example("moisture-shared-balance")
    next(b for b in at.button if b.label == "Add to report").click().run()
    _, info = budget_from_record(at.session_state["records"][0])
    assert info["correlation"] and len(info["correlation"]) == 3
