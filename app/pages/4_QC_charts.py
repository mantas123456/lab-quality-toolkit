"""QC charts page: Levey-Jennings chart with Westgard rules (labqc.control_charts)."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import (
    STATUS_COLOURS,
    columns,
    csv_bytes,
    demo_table,
    examples,
    export_header,
    footer,
    friendly_errors,
    page,
    report_button,
)

from labqc.control_charts import REJECT_RULES, Limits, limits_from_data, westgard
from labqc.report import RunRecord

page(
    "QC charts",
    "Daily control results on a Levey-Jennings chart, checked with the Westgard multirules. "
    "The example is examples/westgard_iqc.py: a +1.4 mg/kg shift from day 45.",
)
RULES = ("1_2s", *REJECT_RULES)


def load_example() -> None:
    st.session_state.qc_table = demo_table("qc_daily")
    st.session_state.qc_mode = "From the first results"
    st.session_state.qc_baseline = examples()["qc"]["baseline_points"]
    st.session_state.qc_method = "sd"
    st.session_state.qc_centre = 50.0
    st.session_state.qc_sd = 1.0


def load_upload() -> None:
    file = st.session_state.get("qc_upload")
    if file is None:
        return
    try:
        st.session_state.qc_table = pd.read_csv(file)
        st.session_state.pop("qc_upload_error", None)
    except Exception:  # any parser problem becomes a plain message below
        st.session_state.qc_upload_error = "Could not read the file as CSV."


if "qc_table" not in st.session_state:
    load_example()

inputs, results = columns()

with inputs:
    st.subheader("Inputs")
    st.button("Load example data", on_click=load_example)
    st.file_uploader(
        "Upload a CSV with a value column (and optionally day or date)",
        type="csv",
        key="qc_upload",
        on_change=load_upload,
    )
    if "qc_upload_error" in st.session_state:
        st.error(st.session_state.qc_upload_error)
    mode = st.radio(
        "Control limits", ["From the first results", "Enter centre and SD"], key="qc_mode"
    )
    if mode == "From the first results":
        c1, c2 = st.columns(2)
        n_base = c1.number_input("Baseline results", min_value=2, step=1, key="qc_baseline")
        method = c2.selectbox("SD from", ["sd", "moving_range"], key="qc_method")
    else:
        c1, c2 = st.columns(2)
        centre = c1.number_input("Centre (target)", key="qc_centre", format="%.4f")
        sd_in = c2.number_input("SD", min_value=0.0, key="qc_sd", format="%.4f")
    data = st.session_state.qc_table
    st.dataframe(data, height=260, width="stretch", hide_index=True)

with results:
    st.subheader("Results")
    with friendly_errors():
        if "value" not in data.columns:
            raise ValueError("The CSV needs a column named value")
        values = pd.to_numeric(data["value"], errors="raise").to_numpy()
        x_col = next((c for c in ("day", "date", "run") if c in data.columns), None)
        x = data[x_col].to_numpy() if x_col else list(range(1, len(values) + 1))
        if mode == "From the first results":
            n_base = int(n_base)
            if n_base >= len(values):
                raise ValueError("Leave at least one result after the baseline to check")
            limits = limits_from_data(values[:n_base], method=method)
        else:
            if sd_in <= 0:
                raise ValueError("SD must be greater than 0")
            n_base = 0
            limits = Limits(centre, sd_in)
        if limits.sd <= 0:
            raise ValueError("The baseline SD is 0: the baseline results are all identical")
        table = westgard(values[n_base:], limits)
    table.insert(0, x_col or "run", x[n_base:])
    table["rules"] = table[list(RULES)].apply(lambda r: ", ".join(r.index[r]), axis=1)

    counts = table["status"].value_counts()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Centre", f"{limits.centre:.4g}")
    m2.metric("SD", f"{limits.sd:.3g}")
    m3.metric("Warnings", int(counts.get("warning", 0)))
    m4.metric("Rejects", int(counts.get("reject", 0)))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x, y=values, mode="lines", line={"color": "#bbb", "width": 1}, showlegend=False
        )
    )
    if n_base:
        fig.add_trace(
            go.Scatter(
                x=x[:n_base], y=values[:n_base], mode="markers", name="Baseline",
                marker={"color": "#999", "size": 6},
            )
        )  # fmt: skip
    for status, colour in STATUS_COLOURS.items():
        part = table[table["status"] == status]
        fig.add_trace(
            go.Scatter(
                x=part.iloc[:, 0], y=part["value"], mode="markers", name=status.capitalize(),
                marker={"color": colour, "size": 9}, text=part["rules"],
                hovertemplate="%{x}: %{y}<br>%{text}<extra></extra>",
            )
        )  # fmt: skip
    for n, dash in [(0, "solid"), (1, "dot"), (-1, "dot"), (2, "dash"), (-2, "dash"),
                    (3, "solid"), (-3, "solid")]:  # fmt: skip
        fig.add_hline(
            y=limits.line(n), line_dash=dash, line_width=1,
            line_color="black" if abs(n) == 3 else "grey",
            annotation_text=f"{n:+d} SD" if n else "centre", annotation_position="right",
        )  # fmt: skip
    fig.update_layout(
        height=420, margin={"t": 30, "r": 60}, xaxis_title=x_col or "run",
        yaxis_title="Control result", legend={"orientation": "h", "y": 1.08},
    )  # fmt: skip
    st.plotly_chart(fig, width="stretch")

    flagged = table[table["status"] != "accept"]
    if flagged.empty:
        st.success("All results accepted.")
    else:
        st.markdown("**Flagged results**")
        st.dataframe(
            flagged[[table.columns[0], "value", "z", "status", "rules"]],
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "1_2s alone is a warning. 1_3s and R_4s point to random error; "
            "2_2s, 4_1s and 10_x to systematic error such as calibration."
        )

export_header()
st.download_button(
    "Download status table (CSV)", csv_bytes(table), "westgard_status.csv", "text/csv"
)
report_button(
    lambda: RunRecord(
        "labqc.control_charts.westgard",
        title="QC chart",
        method=(
            "Levey-Jennings chart; Westgard multirules 1_2s (warning), 1_3s, 2_2s, R_4s, 4_1s "
            "and 10_x (reject) on z = (x - centre) / SD."
        ),
        inputs={"results": data},
        settings={
            "limits": mode,
            "baseline_results": n_base,
            "sd_from": method if n_base else None,
        },
        result={
            "centre": limits.centre,
            "sd": limits.sd,
            "warnings": int(counts.get("warning", 0)),
            "rejects": int(counts.get("reject", 0)),
            "flagged": flagged[[table.columns[0], "value", "z", "status", "rules"]],
        },
    )
)
footer()
