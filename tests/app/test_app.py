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
