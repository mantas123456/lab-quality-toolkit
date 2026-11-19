"""Project files (app/project.py): save the session, check the file, load it back."""

import json

import pandas as pd
import pytest

pytest.importorskip("streamlit")
import project  # noqa: E402  (tests/app/conftest.py puts app/ on the path)

from labqc.report import RunRecord  # noqa: E402


def session():
    return {
        "unc_table": pd.DataFrame({"name": ["a"], "value": [0.1]}),
        "unc_table__edited": pd.DataFrame({"name": ["a", "b"], "value": [0.1, float("nan")]}),
        "unc_y": 6.97,
        "unc_unit": "%",
        "dec_has_lower": False,
        "dec_rule": "guarded",
        "qc_baseline": 20,
        "something_else": object(),  # not an input: not saved
        "records": [RunRecord("labqc.proficiency", {"x": 1.0}, title="PT")],
    }


def test_round_trip_keeps_inputs_edits_and_records():
    text = project.dumps(session(), "1.3.0")
    data = json.loads(text)
    assert data["format"] == "labqc-project" and data["version"] == project.VERSION
    assert set(data["pages"]) == {"uncertainty", "decision", "qc"}
    values, records = project.loads(text)
    table = values["unc_table"]
    assert table["name"].tolist() == ["a", "b"]  # the edited table was saved
    assert table["value"].isna().tolist() == [False, True]
    assert values["unc_y"] == 6.97 and values["dec_has_lower"] is False
    assert values["qc_baseline"] == 20
    assert records[0].title == "PT" and records[0].inputs == {"x": 1.0}


def test_apply_sets_state_and_refreshes_editors():
    state = {"unc_version": 3, "unc_table__edited": "stale"}
    values, records = project.loads(project.dumps(session(), "1.3.0"))
    project.apply(state, values, records)
    assert state["unc_y"] == 6.97
    assert "unc_table__edited" not in state
    assert state["unc_version"] == 4 and state["em_version"] == 1
    assert len(state["records"]) == 1


def good() -> dict:
    return json.loads(project.dumps(session(), "1.3.0"))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(format="other"), "not a labqc project file"),
        (lambda d: d.update(version=project.VERSION + 1), "saved by a newer labqc"),
        (lambda d: d.update(version="1"), "no valid version"),
        (lambda d: d.update(extra=1), "Unknown entries"),
        (lambda d: d["pages"].update(cooking={}), "Unknown page"),
        (lambda d: d["pages"]["qc"].update(qc_colour="red"), "unknown input 'qc_colour'"),
        (lambda d: d["pages"]["uncertainty"]["unc_table"]["rows"].append([1]), "row 3 must have"),
        (lambda d: d["pages"]["uncertainty"].update(unc_y=[1, 2]), "must be a number, text"),
        (lambda d: d.update(records=[{"function": "x", "colour": 1}]), "Record 1"),
    ],
)
def test_schema_check_refuses_bad_files(change, message):
    data = good()
    change(data)
    with pytest.raises(ValueError, match=message):
        project.loads(json.dumps(data))


def test_not_json_is_refused():
    with pytest.raises(ValueError, match="not valid JSON"):
        project.loads("{not json")
