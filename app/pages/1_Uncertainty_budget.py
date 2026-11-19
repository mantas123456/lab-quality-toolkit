"""Uncertainty budget page: components table -> labqc.uncertainty.combine."""

import explain
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from common import (
    CORR_COLUMNS,
    columns,
    correlation_dict,
    correlation_frame,
    csv_bytes,
    deep_link,
    demo_table,
    examples,
    export_header,
    footer,
    friendly_errors,
    page,
    report_button,
    what_this_means,
)

from labqc.report import record_budget
from labqc.uncertainty import (
    DIVISORS,
    TABLE_COLUMNS,
    combine,
    compare_with_monte_carlo,
    components_from_table,
    monte_carlo_budget,
)

PAGE = "pages/1_Uncertainty_budget.py"
MC_TRIALS = 200_000
MC_SEED = 2026

page(
    "Uncertainty budget",
    "GUM (JCGM 100) budget, with optional correlations between inputs and a Monte Carlo "
    "check (JCGM 101). The example is the moisture determination from "
    "examples/moisture_uncertainty.py.",
)


def load_example() -> None:
    st.session_state.unc_table = demo_table("moisture_budget")
    st.session_state.unc_y = examples()["moisture"]["y"]
    st.session_state.unc_unit = examples()["moisture"]["unit"]
    st.session_state.unc_coverage = 0.95
    st.session_state.unc_k = 0.0
    st.session_state.unc_corr = correlation_frame(None)
    st.session_state.unc_version = st.session_state.get("unc_version", 0) + 1


def load_shared_balance() -> None:
    """The moisture budget with one balance for all three weighings (monte_carlo_vs_gum.py)."""
    load_example()
    r = examples()["moisture"]["r_shared_balance"]
    names = ["Weighing m1", "Weighing m2", "Weighing m3"]
    pairs = {(a, b): r for i, a in enumerate(names) for b in names[i + 1 :]}
    st.session_state.unc_corr = correlation_frame(pairs)


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


deep_link(PAGE, {"moisture": load_example, "moisture-shared-balance": load_shared_balance})
if "unc_table" not in st.session_state:
    load_example()
st.session_state.setdefault("unc_corr", correlation_frame(None))

inputs, results = columns()

with inputs:
    st.subheader("Inputs")
    st.button("Load example data", on_click=load_example)
    c1, c2 = st.columns(2)
    y = c1.number_input("Measured value y", key="unc_y", format="%.4f")
    unit = c2.text_input("Unit of y", key="unc_unit")
    c1, c2 = st.columns(2)
    coverage = c1.selectbox(
        "Coverage", [0.90, 0.95, 0.99], key="unc_coverage", format_func=lambda p: f"{p:.0%}"
    )
    fixed_k = c2.number_input("Fixed k (0 = from v_eff)", min_value=0.0, step=0.5, key="unc_k")
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
    names = [str(n) for n in table["name"].dropna()] if "name" in table.columns else []
    with st.expander("Correlated inputs (optional)", expanded=not st.session_state.unc_corr.empty):
        st.caption(
            "One row per pair of correlated components, with r between -1 and 1. A shared "
            "balance or reference standard behind several inputs is the usual cause."
        )
        corr_table = st.data_editor(
            st.session_state.unc_corr,
            key=f"unc_corr_editor_{st.session_state.unc_version}",
            num_rows="dynamic",
            width="stretch",
            column_config={
                CORR_COLUMNS[0]: st.column_config.SelectboxColumn(CORR_COLUMNS[0], options=names),
                CORR_COLUMNS[1]: st.column_config.SelectboxColumn(CORR_COLUMNS[1], options=names),
                CORR_COLUMNS[2]: st.column_config.NumberColumn(
                    CORR_COLUMNS[2], min_value=-1.0, max_value=1.0, format="%.3f"
                ),
            },
        )

with results:
    st.subheader("Results")
    with friendly_errors():
        components = components_from_table(table)
        correlation = correlation_dict(corr_table)
        result = combine(
            components,
            coverage=coverage,
            k=fixed_k or None,
            correlation=correlation,
            value=y if y else None,
        )
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
    if correlation:
        st.caption(
            f"Correlations add {result.covariance:+.3g} to u_c², so the shares of variance "
            "do not sum to 100 %."
        )
    what_this_means(explain.uncertainty(budget, result.k, result.effective_dof, result.covariance))

    st.markdown("**Check with Monte Carlo** (JCGM 101)")
    c1, c2 = st.columns(2, vertical_alignment="bottom")
    n_dig = c1.selectbox(
        "Significant digits for δ",
        [2, 1],
        key="unc_n_dig",
        help="The tolerance δ is half a unit in the last of these digits of u(y).",
    )
    run_mc = c2.button("Check with Monte Carlo", help=f"{MC_TRIALS:,} trials, seed {MC_SEED}")
    if run_mc:
        try:
            mc = monte_carlo_budget(
                components, y, correlation, n=MC_TRIALS, seed=MC_SEED, coverage=coverage
            )
            agreement = compare_with_monte_carlo(y, result, mc, n_dig=n_dig)
        except ValueError as err:
            st.error(str(err))
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("GUM interval", f"[{agreement.gum_low:.4g}, {agreement.gum_high:.4g}]")
            m2.metric("Monte Carlo interval", f"[{mc.low:.4g}, {mc.high:.4g}]")
            m3.metric(
                "Agreement",
                "confirmed" if agreement.agrees else "not confirmed",
                help=(
                    f"d_low = {agreement.d_low:.2g}, d_high = {agreement.d_high:.2g}, "
                    f"δ = {agreement.delta:.2g}"
                ),
            )
            hist = go.Figure(go.Histogram(x=mc.samples, nbinsx=80, marker_color="#9bbcd0"))
            for x_line, colour, dash in (
                (agreement.gum_low, "#2c6e8f", "dash"),
                (agreement.gum_high, "#2c6e8f", "dash"),
                (mc.low, "#c0392b", "dot"),
                (mc.high, "#c0392b", "dot"),
            ):
                hist.add_vline(x=x_line, line_color=colour, line_dash=dash)
            hist.update_layout(
                height=260,
                margin={"t": 30},
                showlegend=False,
                title="Monte Carlo values of y: GUM ends dashed, Monte Carlo ends dotted",
                xaxis_title=unit or "y",
            )
            st.plotly_chart(hist, width="stretch")
            what_this_means(
                explain.monte_carlo(
                    agreement.agrees,
                    agreement.d_low,
                    agreement.d_high,
                    agreement.delta,
                    n_dig,
                    finite_dof=any(c.dof != float("inf") for c in components),
                )
            )

export_header()
summary = budget.assign(
    y=y, unit=unit, u_c=result.combined, k=result.k, U=result.expanded, coverage=coverage
)
st.download_button(
    "Download budget (CSV)", csv_bytes(summary), "uncertainty_budget.csv", "text/csv"
)
report_button(
    lambda: record_budget(
        components,
        result,
        coverage=coverage,
        fixed_k=fixed_k or None,
        unit=unit,
        correlation=correlation,
    )
)
footer()
