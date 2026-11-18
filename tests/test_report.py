"""Records and reports (labqc.report). Data: the moisture example from examples/, no client data."""

import json
import math

import pytest

from labqc.report import RunRecord, budget_from_record, record_budget, to_excel, to_pdf
from labqc.uncertainty import Component, combine, components_from_table, type_a


@pytest.fixture
def budget():
    comps = [
        type_a([6.97, 7.02, 6.94, 7.05, 6.99], "Repeatability"),
        Component("Balance", 0.001, "normal", sensitivity=0.74, unit="g"),
        Component("Temperature σ", 0.004, "rectangular"),  # non-ASCII name on purpose
    ]
    return comps, combine(comps, value=6.97)


def test_json_round_trip_is_identical(budget):
    comps, result = budget
    record = record_budget(comps, result, unit="%", analyst="A. Analyst")
    text = record.to_json()
    again = RunRecord.from_json(text)
    assert again.to_json() == text
    assert again == record
    data = json.loads(text)  # strict JSON: infinity stored as "inf", not Infinity
    assert data["inputs"]["components"][1]["dof"] == "inf"
    assert data["labqc_version"] and data["timestamp"].endswith("+00:00")


def test_budget_reloads_to_the_same_result(budget):
    comps, result = budget
    record = RunRecord.from_json(record_budget(comps, result, coverage=0.95).to_json())
    table, info = budget_from_record(record)
    again = combine(components_from_table(table), coverage=info["coverage"], value=info["value"])
    assert again.expanded == pytest.approx(result.expanded, rel=1e-12)
    assert again.k == pytest.approx(result.k)
    assert math.isinf(components_from_table(table)[1].dof)


def test_from_json_rejects_other_files():
    with pytest.raises(ValueError, match="Not a valid labqc record"):
        RunRecord.from_json("not json")
    with pytest.raises(ValueError, match="missing"):
        RunRecord.from_json('{"function": "x"}')
    with pytest.raises(ValueError, match="unknown field"):
        RunRecord.from_json('{"function": "x", "inputs": {}, "colour": "red"}')
    other = RunRecord("labqc.validation.linearity", {"concentration": [1, 2, 3]})
    with pytest.raises(ValueError, match="not an uncertainty budget"):
        budget_from_record(other)


def test_excel_one_sheet_per_record(tmp_path, budget):
    openpyxl = pytest.importorskip("openpyxl")
    comps, result = budget
    records = [
        record_budget(comps, result),
        record_budget(comps, result),  # same title: sheet names must still be unique
        RunRecord("labqc.proficiency.z_score", {"x": 10.75}, result={"z": 2.5}, title="PT: z"),
    ]
    path = tmp_path / "records.xlsx"
    to_excel(records, path)
    assert path.stat().st_size > 0
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["Uncertainty budget", "Uncertainty budget 2", "PT- z"]
    values = [c.value for row in wb["Uncertainty budget"].iter_rows() for c in row]
    assert "Balance" in values and result.expanded in values
    with pytest.raises(ValueError):
        to_excel([], tmp_path / "empty.xlsx")


def test_pdf_is_created(tmp_path, budget):
    pytest.importorskip("reportlab")
    comps, result = budget
    path = tmp_path / "budget.pdf"
    to_pdf(record_budget(comps, result, analyst="A. Analyst"), path)
    content = path.read_bytes()
    assert content.startswith(b"%PDF") and len(content) > 1500
