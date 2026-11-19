"""QC overview (labqc.control_charts.qc_overview): latest-run status per method and level."""

from pathlib import Path

import pandas as pd
import pytest

from labqc.control_charts import limits_from_data, qc_overview


def frame(method, level, values, target=None, sd=None):
    return pd.DataFrame(
        {
            "date": [f"2026-01-{i + 1:02d}" for i in range(len(values))],
            "method": method,
            "level": level,
            "value": values,
            "target": target,
            "sd": sd,
        }
    )


def test_assigned_target_and_sd_are_used_from_the_first_result():
    """z = 0, 2.5, 3.5 against 100 +/- 1: the last run breaks 1_2s, 1_3s and 2_2s."""
    out = qc_overview(frame("A", "low", [100.0, 102.5, 103.5], 100.0, 1.0))
    row = out.iloc[0]
    assert (row["limits_from"], row["baseline_n"], row["n"]) == ("target", 0, 3)
    assert row["status"] == "reject"
    assert row["rules"] == "1_2s, 1_3s, 2_2s"
    assert (row["warnings"], row["rejects"]) == (1, 1)
    assert row["last_z"] == pytest.approx(3.5)


def test_limits_from_the_baseline_when_no_target():
    values = [9.0, 11.0] * 10 + [10.0, 12.2]
    out = qc_overview(frame("B", "high", values), baseline=20)
    row = out.iloc[0]
    lim = limits_from_data(values[:20])
    assert row["centre"] == pytest.approx(lim.centre)
    assert row["sd"] == pytest.approx(lim.sd)
    assert row["limits_from"] == "first 20 results"
    assert row["status"] == "warning"  # z = 2.2 / 1.026 = 2.14
    assert row["last_date"] == "2026-01-22"


def test_rows_in_order_of_first_appearance_and_sorted_by_date():
    a = frame("A", "low", [100.0, 100.5], 100.0, 1.0)
    b = frame("B", "low", [5.0, 5.1], 5.0, 0.1)
    data = pd.concat([b, a.iloc[::-1]], ignore_index=True)  # A given newest first
    out = qc_overview(data)
    assert out["method"].tolist() == ["B", "A"]
    assert out.iloc[1]["last_value"] == 100.5


def test_demo_data_has_one_reject_and_one_warning():
    demo = Path(__file__).resolve().parents[1] / "app" / "demo_data" / "qc_overview.csv"
    out = qc_overview(pd.read_csv(demo))
    status = dict(zip(zip(out["method"], out["level"], strict=True), out["status"], strict=True))
    assert status.pop(("Ash (550 °C)", "high")) == "reject"
    assert status.pop(("Moisture (oven)", "low")) == "warning"
    assert set(status.values()) == {"accept"}


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (pd.DataFrame({"method": ["A"], "value": [1.0]}), "needs the column"),
        (frame("A", "low", [1.0, 2.0, 3.0]), "needs more than the 20 baseline"),
        (frame("A", "low", [1.0, 2.0], 1.0, 0.0), "SD must be greater than 0"),
        (frame("A", "low", []), "no results"),
    ],
)
def test_qc_overview_errors(data, message):
    with pytest.raises(ValueError, match=message):
        qc_overview(data)
