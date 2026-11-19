"""Equipment drift page: error against time from calibration certificates, and the
calibration interval (labqc.equipment)."""

import explain
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import (
    columns,
    csv_bytes,
    deep_link,
    demo_table,
    examples,
    export_header,
    footer,
    friendly_errors,
    page,
    remember,
    report_button,
    what_this_means,
)

from labqc.equipment import drift
from labqc.report import RunRecord

PAGE = "pages/8_Equipment_drift.py"
SUGGESTION_COLOURS = {"shorten": "red", "keep": "blue", "lengthen": "green"}

page(
    "Equipment drift",
    "The error from successive calibration certificates, fitted against time: drift per "
    "year, when |error| + U is predicted to reach the tolerance, and whether the "
    "calibration interval should change.",
)


def load_example() -> None:
    ex = examples()["equipment"]
    st.session_state.eq_table = demo_table("equipment")
    st.session_state.eq_tolerance = ex["tolerance"]
    st.session_state.eq_unit = ex["unit"]
    st.session_state.eq_interval = 0.0
    st.session_state.eq_version = st.session_state.get("eq_version", 0) + 1


deep_link(PAGE, {"equipment-drift": load_example})
if "eq_table" not in st.session_state:
    load_example()

inputs, results = columns()

with inputs:
    st.subheader("Inputs")
    st.button("Load example data", on_click=load_example)
    st.caption(f"Example: {examples()['equipment']['what']} (illustrative values).")
    st.markdown("**Certificates**, oldest first: date, error at the check point, U")
    table = st.data_editor(
        st.session_state.eq_table,
        key=f"eq_editor_{st.session_state.eq_version}",
        num_rows="dynamic",
        width="stretch",
    )
    remember("eq_table", table)
    c1, c2, c3 = st.columns(3)
    tolerance = c1.number_input("Tolerance (±)", min_value=0.0, key="eq_tolerance", format="%.4g")
    unit = c2.text_input("Unit", key="eq_unit")
    interval_in = c3.number_input(
        "Current interval (years, 0 = from the dates)", min_value=0.0, step=0.5,
        key="eq_interval",
    )  # fmt: skip

with results:
    st.subheader("Drift")
    with friendly_errors():
        rows = table.dropna(how="all")
        if not {"date", "error", "U"} <= set(rows.columns):
            raise ValueError("The table needs columns date, error and U")
        d = drift(
            rows["date"].astype(str).tolist(),
            pd.to_numeric(rows["error"], errors="raise"),
            pd.to_numeric(rows["U"], errors="raise"),
            tolerance,
            interval_years=interval_in or None,
        )
    u = f" {unit}" if unit else ""
    m1, m2, m3 = st.columns(3)
    m1.metric("Drift per year", f"{d.drift_per_year:+.3g}{u}")
    m2.metric("Reaches the tolerance", "never" if d.reach_date is None else f"{d.reach_date}")
    m3.metric("Current interval", f"{d.interval_years:.2g} years")
    colour = SUGGESTION_COLOURS[d.suggestion]
    st.markdown(
        f"Suggested interval: :{colour}[**{d.suggestion} → {d.suggested_interval_years:.2g} "
        "years**]"
    )

    dates = pd.to_datetime(d.table["date"])
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates, y=d.table["error"], mode="markers", name="error ± U",
            error_y={"type": "data", "array": d.table["U"], "visible": True},
            marker={"size": 10, "color": "#2c6e8f"},
        )
    )  # fmt: skip
    end = d.reach_date or (dates.iloc[-1] + pd.Timedelta(days=365 * 3)).date()
    span = pd.to_datetime([dates.iloc[0], max(pd.Timestamp(end), dates.iloc[-1])])
    years = (span - dates.iloc[0]).days / 365.25
    fig.add_trace(
        go.Scatter(x=span, y=d.intercept + d.drift_per_year * years, mode="lines",
                   name="fitted drift", line={"color": "#c0392b", "dash": "dot"})
    )  # fmt: skip
    for edge in (d.tolerance, -d.tolerance):
        fig.add_hline(y=edge, line_color="black", line_width=1, line_dash="dash")
    fig.add_hline(y=0, line_color="grey", line_width=1)
    if d.reach_date is not None:
        fig.add_vline(x=pd.Timestamp(d.reach_date).timestamp() * 1000, line_color="#c0392b",
                      line_width=1, annotation_text="reaches tolerance")  # fmt: skip
    fig.update_layout(height=360, margin={"t": 30}, yaxis_title=f"error{u}",
                      legend={"orientation": "h", "y": 1.1})  # fmt: skip
    st.plotly_chart(fig, width="stretch")
    what_this_means(explain.drift(d, unit))
    st.dataframe(d.table, hide_index=True, width="stretch")
    st.caption(
        "Rule: shorten if |error| + U is predicted to reach the tolerance within the current "
        "interval; lengthen (to 1.5 x at most) if that is at least two intervals away and every "
        "certificate had |error| + U within half the tolerance; otherwise keep. A line from "
        "few certificates is weak evidence: decide with the use and checks of the instrument."
    )

export_header()
st.download_button("Download table (CSV)", csv_bytes(d.table), "equipment_drift.csv", "text/csv")
report_button(
    lambda: RunRecord(
        "labqc.equipment.drift",
        title="Equipment drift",
        method=(
            "Least-squares line of certificate error against time; tolerance reached when "
            "|predicted error| + U equals it; interval rule: shorten / keep / lengthen as "
            "stated on the page."
        ),
        inputs={"certificates": rows, "tolerance": tolerance, "unit": unit},
        settings={"interval_years": d.interval_years},
        result={
            "drift_per_year": d.drift_per_year,
            "reach_date": None if d.reach_date is None else str(d.reach_date),
            "suggestion": d.suggestion,
            "suggested_interval_years": d.suggested_interval_years,
            "reason": d.reason,
        },
    )
)
footer()
