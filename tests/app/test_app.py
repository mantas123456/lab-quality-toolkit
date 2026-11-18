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
