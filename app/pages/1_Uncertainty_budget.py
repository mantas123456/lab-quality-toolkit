"""Uncertainty budget page: components table -> labqc.uncertainty.combine."""

import plotly.express as px
import streamlit as st
from common import (
    columns,
    csv_bytes,
    demo_table,
    examples,
    export_header,
    footer,
    friendly_errors,
    page,
)

from labqc.uncertainty import DIVISORS, TABLE_COLUMNS, combine, components_from_table

page(
    "Uncertainty budget",
    "GUM (JCGM 100) budget for uncorrelated inputs. The example is the moisture "
    "determination from examples/moisture_uncertainty.py.",
)


def load_example() -> None:
    st.session_state.unc_table = demo_table("moisture_budget")
    st.session_state.unc_y = examples()["moisture"]["y"]
    st.session_state.unc_unit = examples()["moisture"]["unit"]
    st.session_state.unc_version = st.session_state.get("unc_version", 0) + 1


def load_upload() -> None:
    import pandas as pd

    file = st.session_state.get("unc_upload")
    if file is None:
        return
    try:
        st.session_state.unc_table = pd.read_csv(file)
    except Exception:  # any parser problem becomes a plain message below
        st.session_state.unc_upload_error = "Could not read the file as CSV."
        return
    st.session_state.pop("unc_upload_error", None)
    st.session_state.unc_version = st.session_state.get("unc_version", 0) + 1


if "unc_table" not in st.session_state:
    load_example()

inputs, results = columns()

with inputs:
    st.subheader("Inputs")
    st.button("Load example data", on_click=load_example)
    c1, c2 = st.columns(2)
    y = c1.number_input("Measured value y", key="unc_y", format="%.4f")
    unit = c2.text_input("Unit of y", key="unc_unit")
    c1, c2 = st.columns(2)
    coverage = c1.selectbox(
        "Coverage", [0.90, 0.95, 0.99], index=1, format_func=lambda p: f"{p:.0%}"
    )
    fixed_k = c2.number_input(
        "Fixed k (0 = from v_eff)", min_value=0.0, value=0.0, step=0.5, key="unc_k"
    )
    st.markdown(
        "**Components.** For *normal*, value is a standard uncertainty (or an expanded one "
        "with its k). For the other distributions, value is the half-width. Blank dof = infinite."
    )
    table = st.data_editor(
        st.session_state.unc_table,
        key=f"unc_editor_{st.session_state.unc_version}",
        num_rows="dynamic",
        width="stretch",
        column_config={
            "distribution": st.column_config.SelectboxColumn(
                "distribution", options=list(DIVISORS), default="normal"
            ),
        },
    )
    st.file_uploader(
        f"Or upload a CSV with columns {', '.join(TABLE_COLUMNS)}",
        type="csv",
        key="unc_upload",
        on_change=load_upload,
    )
    if "unc_upload_error" in st.session_state:
        st.error(st.session_state.unc_upload_error)

with results:
    st.subheader("Results")
    with friendly_errors():
        components = components_from_table(table)
        result = combine(components, coverage=coverage, k=fixed_k or None, value=y if y else None)
    dof = "∞" if result.effective_dof == float("inf") else f"{result.effective_dof:.1f}"
    m1, m2, m3 = st.columns(3)
    m1.metric("Result", f"{y:.4g} ± {result.expanded:.2g} {unit}".strip())
    m2.metric(f"U ({coverage:.0%})", f"{result.expanded:.4g}")
    m3.metric("k", f"{result.k:.2f}", help=f"effective degrees of freedom v_eff = {dof}")
    m1, m2, m3 = st.columns(3)
    m1.metric("u_c", f"{result.combined:.4g}")
    m2.metric("v_eff", dof)
    if result.value:
        m3.metric("U relative", f"{result.relative_expanded:.2%}")
    st.caption(result.summary(relative=bool(result.value)))

    budget = result.table
    st.dataframe(
        budget.style.format(
            {
                "u_i": "{:.3g}",
                "c_i": "{:.3g}",
                "contribution": "{:.3g}",
                "share_of_variance": "{:.1%}",
            }
        ),
        width="stretch",
        hide_index=True,
    )
    fig = px.bar(
        budget.iloc[::-1],
        x="share_of_variance",
        y="component",
        orientation="h",
        labels={"share_of_variance": "Share of variance", "component": ""},
        title="Where the uncertainty comes from",
    )
    fig.update_layout(xaxis_tickformat=".0%", height=120 + 40 * len(budget), margin={"l": 10})
    fig.update_traces(marker_color="#2c6e8f")
    st.plotly_chart(fig, width="stretch")
    top = budget.iloc[0]
    st.info(
        f"**{top['component']}** gives {top['share_of_variance']:.0%} of the variance: "
        "improve that first."
    )

export_header()
summary = budget.assign(
    y=y, unit=unit, u_c=result.combined, k=result.k, U=result.expanded, coverage=coverage
)
st.download_button(
    "Download budget (CSV)", csv_bytes(summary), "uncertainty_budget.csv", "text/csv"
)
footer()
