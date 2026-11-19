"""QC overview page: Westgard status of every method and control level at a glance
(labqc.control_charts.qc_overview)."""

import explain
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import (
    STATUS_COLOURS,
    columns,
    csv_bytes,
    deep_link,
    demo_table,
    export_header,
    footer,
    friendly_errors,
    page,
    report_button,
    what_this_means,
)

from labqc.control_charts import Limits, qc_overview, westgard
from labqc.report import RunRecord

PAGE = "pages/5_QC_overview.py"
ICONS = {"accept": "🟢", "warning": "🟡", "reject": "🔴"}

page(
    "QC overview",
    "Every method and control level in one grid, coloured by the Westgard status of the latest "
    "run. Click a cell to see its chart, or open the series on the QC charts page.",
)


def load_example() -> None:
    st.session_state.qcov_table = demo_table("qc_overview")
    st.session_state.qcov_baseline = 20
    st.session_state.qcov_method = "sd"
    st.session_state.pop("qcov_selected", None)


def load_upload() -> None:
    file = st.session_state.get("qcov_upload")
    if file is None:
        return
    try:
        st.session_state.qcov_table = pd.read_csv(file)
        st.session_state.pop("qcov_upload_error", None)
        st.session_state.pop("qcov_selected", None)
    except Exception:  # any parser problem becomes a plain message below
        st.session_state.qcov_upload_error = "Could not read the file as CSV."


def select(method: str, level: str) -> None:
    st.session_state.qcov_selected = (method, level)


def open_in_qc_charts(series: pd.DataFrame, row: pd.Series) -> None:
    """Load one series into the QC charts page with the same limits."""
    st.session_state.qc_table = series[["date", "value"]].reset_index(drop=True)
    if row["limits_from"] == "target":
        st.session_state.qc_mode = "Enter centre and SD"
        st.session_state.qc_centre = float(row["centre"])
        st.session_state.qc_sd = float(row["sd"])
    else:
        st.session_state.qc_mode = "From the first results"
        st.session_state.qc_baseline = int(row["baseline_n"])
        st.session_state.qc_method = st.session_state.qcov_method
    st.session_state.qc_across = False
    st.session_state.qc_tab_default = "Westgard"
    st.session_state.pop("qc_level", None)


deep_link(PAGE, {"qc-overview": load_example})
if "qcov_table" not in st.session_state:
    load_example()

inputs, results = columns()

with inputs:
    st.subheader("Inputs")
    st.button("Load example data", on_click=load_example)
    st.file_uploader(
        "Upload a CSV with columns date, method, level, value (optionally target and sd)",
        type="csv",
        key="qcov_upload",
        on_change=load_upload,
    )
    if "qcov_upload_error" in st.session_state:
        st.error(st.session_state.qcov_upload_error)
    c1, c2 = st.columns(2)
    baseline = c1.number_input(
        "Baseline results (series without target and sd)", min_value=2, step=1,
        key="qcov_baseline",
    )  # fmt: skip
    sd_method = c2.selectbox("SD from", ["sd", "moving_range"], key="qcov_method")
    data = st.session_state.qcov_table
    st.dataframe(data, height=320, width="stretch", hide_index=True)

with results:
    st.subheader("Latest run")
    with friendly_errors():
        overview = qc_overview(data, baseline=int(baseline), method=sd_method)
    counts = overview["status"].value_counts()
    m1, m2, m3 = st.columns(3)
    m1.metric("Series", len(overview))
    m2.metric("Warnings", int(counts.get("warning", 0)))
    m3.metric("Rejects", int(counts.get("reject", 0)))

    levels = list(dict.fromkeys(overview["level"]))
    header = st.columns([1.4, *[1] * len(levels)])
    header[0].markdown("**Method**")
    for col, level in zip(header[1:], levels, strict=True):
        col.markdown(f"**{level}**")
    for method, rows in overview.groupby("method", sort=False):
        cells = st.columns([1.4, *[1] * len(levels)])
        cells[0].markdown(method)
        for col, level in zip(cells[1:], levels, strict=True):
            hit = rows[rows["level"] == level]
            if hit.empty:
                col.markdown("–")
                continue
            r = hit.iloc[0]
            label = f"{ICONS[r['status']]} {r['status']}" + (
                f" ({r['rules']})" if r["rules"] else ""
            )
            col.button(
                label, key=f"qcov_{method}_{level}", on_click=select, args=(method, level),
                help=f"latest {r['last_date']}: {r['last_value']:.4g} (z = {r['last_z']:+.2f})",
                width="stretch",
            )  # fmt: skip
    what_this_means(explain.qc_overview(overview))

    selected = st.session_state.get("qcov_selected")
    if selected is None:
        bad = overview[overview["status"] != "accept"]
        first = bad.iloc[0] if len(bad) else overview.iloc[0]
        selected = (first["method"], first["level"])
    row = overview[(overview["method"] == selected[0]) & (overview["level"] == selected[1])]
    if not row.empty:
        row = row.iloc[0]
        series = data[(data["method"] == row["method"]) & (data["level"] == row["level"])]
        series = series.sort_values("date", kind="stable")
        limits = Limits(float(row["centre"]), float(row["sd"]))
        n_base = int(row["baseline_n"])
        table = westgard(series["value"].to_numpy()[n_base:], limits)
        x = series["date"].to_numpy()
        st.markdown(f"**{row['method']} / {row['level']}**")
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(x=x, y=series["value"], mode="lines", line={"color": "#bbb", "width": 1},
                       showlegend=False)
        )  # fmt: skip
        if n_base:
            fig.add_trace(
                go.Scatter(x=x[:n_base], y=series["value"].to_numpy()[:n_base], mode="markers",
                           name="Baseline", marker={"color": "#999", "size": 6})
            )  # fmt: skip
        for status, colour in STATUS_COLOURS.items():
            part = table["status"] == status
            fig.add_trace(
                go.Scatter(x=x[n_base:][part.to_numpy()], y=table["value"][part], mode="markers",
                           name=status.capitalize(), marker={"color": colour, "size": 9})
            )  # fmt: skip
        for n_sd, dash in [(0, "solid"), (2, "dash"), (-2, "dash"), (3, "solid"), (-3, "solid")]:
            fig.add_hline(y=limits.line(n_sd), line_dash=dash, line_width=1,
                          line_color="black" if abs(n_sd) == 3 else "grey")  # fmt: skip
        fig.update_layout(height=320, margin={"t": 20}, legend={"orientation": "h", "y": 1.12})
        st.plotly_chart(fig, width="stretch")
        if st.button(
            "Open this series in QC charts", on_click=open_in_qc_charts, args=(series, row)
        ):
            st.switch_page("pages/4_QC_charts.py")

export_header()
st.download_button("Download overview (CSV)", csv_bytes(overview), "qc_overview.csv", "text/csv")
report_button(
    lambda: RunRecord(
        "labqc.control_charts.qc_overview",
        title="QC overview",
        method=(
            "Westgard multirules (1_2s warning; 1_3s, 2_2s, R_4s, 4_1s, 10_x reject) per method "
            "and control level; limits from the assigned target and SD, or from the first "
            f"{int(baseline)} results ({sd_method}); status of the latest run."
        ),
        inputs={"results": data},
        settings={"baseline": int(baseline), "sd_from": sd_method},
        result={"overview": overview},
    )
)
footer()
