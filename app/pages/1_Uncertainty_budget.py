"""Uncertainty budget page: components table -> labqc.uncertainty.combine."""

import explain
import pandas as pd
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
    parse_numbers,
    remember,
    report_button,
    tabs,
    what_this_means,
)

from labqc.report import RunRecord, record_budget
from labqc.topdown import (
    combine_topdown,
    s_r_duplicates,
    u_bias_crm,
    u_bias_pt,
    u_rw,
)
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
    "check (JCGM 101), or top-down from QC and PT or CRM data (Nordtest TR 537). The budget "
    "example is the moisture determination from examples/moisture_uncertainty.py.",
)
TABS = ["GUM budget", "Top-down (Nordtest)"]


def load_example() -> None:
    st.session_state.unc_table = demo_table("moisture_budget")
    st.session_state.unc_y = examples()["moisture"]["y"]
    st.session_state.unc_unit = examples()["moisture"]["unit"]
    st.session_state.unc_coverage = 0.95
    st.session_state.unc_k = 0.0
    st.session_state.unc_corr = correlation_frame(None)
    st.session_state.pop("unc_template_loaded", None)
    st.session_state.unc_version = st.session_state.get("unc_version", 0) + 1


def load_template() -> None:
    """Start a budget from a template; its 'source' column says where each number comes from."""
    key = st.session_state.unc_template
    template = examples()["templates"][key]
    st.session_state.unc_table = pd.DataFrame(template["rows"])
    st.session_state.unc_y = template["y"]
    st.session_state.unc_unit = template["unit"]
    st.session_state.unc_coverage = 0.95
    st.session_state.unc_k = 0.0
    st.session_state.unc_corr = correlation_frame(None)
    st.session_state.unc_template_loaded = key
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


TD_SOURCES = ["PT rounds", "CRM"]


def load_topdown() -> None:
    crm = examples()["topdown_crm"]
    st.session_state.td_qc = demo_table("topdown_qc")
    st.session_state.td_dup = pd.DataFrame({"first": [], "second": []}, dtype=float)
    st.session_state.td_pt = demo_table("topdown_pt")
    st.session_state.td_crm_results = ", ".join(str(v) for v in crm["results"])
    st.session_state.td_crm_certified = crm["certified"]
    st.session_state.td_crm_u = crm["u"]
    st.session_state.td_source = TD_SOURCES[0]
    st.session_state.td_relative = False
    st.session_state.td_k = 2.0
    st.session_state.td_version = st.session_state.get("td_version", 0) + 1


def load_td_upload(key: str, target: str) -> None:
    file = st.session_state.get(key)
    if file is None:
        return
    try:
        st.session_state[target] = pd.read_csv(file)
    except Exception:  # any parser problem becomes a plain message below
        st.session_state.td_upload_error = "Could not read the file as CSV."
        return
    st.session_state.pop("td_upload_error", None)
    st.session_state.td_version = st.session_state.get("td_version", 0) + 1


def open_tab(name: str, loader) -> None:
    loader()
    st.session_state.unc_tab_default = name


deep_link(
    PAGE,
    {
        "moisture": lambda: open_tab(TABS[0], load_example),
        "moisture-shared-balance": lambda: open_tab(TABS[0], load_shared_balance),
        "topdown": lambda: open_tab(TABS[1], load_topdown),
    },
)
if "unc_table" not in st.session_state:
    load_example()
st.session_state.setdefault("unc_corr", correlation_frame(None))
if "td_qc" not in st.session_state:
    load_topdown()

tab_budget, tab_topdown = tabs(TABS, default=st.session_state.get("unc_tab_default", TABS[0]))

with tab_budget:
    inputs, results = columns()

    with inputs:
        st.subheader("Inputs")
        st.button("Load example data", on_click=load_example)
        templates = examples()["templates"]
        c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
        c1.selectbox(
            "Start from a template",
            list(templates),
            format_func=lambda key: templates[key]["title"],
            key="unc_template",
        )
        c2.button("Load template", on_click=load_template)
        loaded = st.session_state.get("unc_template_loaded")
        if loaded:
            st.caption(
                f"Template: {templates[loaded]['title']}. {templates[loaded]['note']} Replace "
                "the numbers with your own; the source column says where each usually comes from."
            )
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
            "with its k). For the other distributions, value is the half-width. "
            "Blank dof = infinite."
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
                "source": st.column_config.TextColumn(
                    "source", help="Where this number usually comes from (not used in the sums)"
                ),
            },
        )
        remember("unc_table", table)
        st.file_uploader(
            f"Or upload a CSV with columns {', '.join(TABLE_COLUMNS)}",
            type="csv",
            key="unc_upload",
            on_change=load_upload,
        )
        if "unc_upload_error" in st.session_state:
            st.error(st.session_state.unc_upload_error)
        names = [str(n) for n in table["name"].dropna()] if "name" in table.columns else []
        with st.expander(
            "Correlated inputs (optional)", expanded=not st.session_state.unc_corr.empty
        ):
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
                    CORR_COLUMNS[0]: st.column_config.SelectboxColumn(
                        CORR_COLUMNS[0], options=names
                    ),
                    CORR_COLUMNS[1]: st.column_config.SelectboxColumn(
                        CORR_COLUMNS[1], options=names
                    ),
                    CORR_COLUMNS[2]: st.column_config.NumberColumn(
                        CORR_COLUMNS[2], min_value=-1.0, max_value=1.0, format="%.3f"
                    ),
                },
            )
            remember("unc_corr", corr_table)

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
        what_this_means(
            explain.uncertainty(budget, result.k, result.effective_dof, result.covariance)
        )

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
with tab_topdown:
    inputs, results = columns()
    with inputs:
        st.subheader("Inputs")
        st.button("Load example data", on_click=load_topdown, key="td_load")
        c1, c2 = st.columns(2)
        relative = c1.toggle(
            "Relative (%)", key="td_relative",
            help="Work in percent of the result, for methods used over a wide range.",
        )  # fmt: skip
        k_td = c2.number_input("k", min_value=1.0, step=0.1, key="td_k")
        st.markdown("**Within-lab reproducibility**: control sample results (column value)")
        qc_table = st.data_editor(
            st.session_state.td_qc,
            key=f"td_qc_editor_{st.session_state.td_version}",
            num_rows="dynamic", width="stretch", height=220,
        )  # fmt: skip
        remember("td_qc", qc_table)
        st.file_uploader(
            "Or upload a CSV with a value column", type="csv", key="td_qc_upload",
            on_change=load_td_upload, args=("td_qc_upload", "td_qc"),
        )  # fmt: skip
        with st.expander("Duplicates of real samples (optional)"):
            st.caption(
                "Add these when the control sample does not go through the whole procedure: "
                "s_r from the pairs is combined with the control SD."
            )
            dup_table = st.data_editor(
                st.session_state.td_dup,
                key=f"td_dup_editor_{st.session_state.td_version}",
                num_rows="dynamic", width="stretch",
            )  # fmt: skip
            remember("td_dup", dup_table)
        st.markdown("**Bias**")
        source = st.radio("Bias from", TD_SOURCES, key="td_source", horizontal=True)
        if source == "PT rounds":
            st.caption("One row per round: your result, the assigned value and its standard u.")
            pt_table = st.data_editor(
                st.session_state.td_pt,
                key=f"td_pt_editor_{st.session_state.td_version}",
                num_rows="dynamic", width="stretch",
            )  # fmt: skip
            remember("td_pt", pt_table)
            st.file_uploader(
                "Or upload a CSV with columns result, assigned, u_assigned", type="csv",
                key="td_pt_upload", on_change=load_td_upload, args=("td_pt_upload", "td_pt"),
            )  # fmt: skip
        else:
            crm_text = st.text_area("Results on the CRM", key="td_crm_results", height=70)
            c1, c2 = st.columns(2)
            certified = c1.number_input("Certified value", key="td_crm_certified", format="%.4g")
            u_cert = c2.number_input(
                "u of the certified value (standard)", min_value=0.0, key="td_crm_u",
                format="%.4g",
            )  # fmt: skip
        if "td_upload_error" in st.session_state:
            st.error(st.session_state.td_upload_error)

    with results:
        st.subheader("Top-down uncertainty (Nordtest TR 537)")
        with friendly_errors():
            if "value" not in qc_table.columns:
                raise ValueError("The control table needs a column named value")
            qc_values = pd.to_numeric(qc_table["value"].dropna(), errors="raise").to_numpy()
            dups = dup_table.dropna(how="any")
            s_r = None
            if len(dups):
                if not {"first", "second"} <= set(dups.columns):
                    raise ValueError("The duplicates table needs columns first and second")
                s_r = s_r_duplicates(
                    pd.to_numeric(dups["first"]), pd.to_numeric(dups["second"]), relative
                )
            urw = u_rw(qc_values, s_r=s_r, relative=relative)
            if source == "PT rounds":
                rounds = pt_table.dropna(how="all")
                needed = {"result", "assigned", "u_assigned"}
                if not needed <= set(rounds.columns):
                    raise ValueError("The PT table needs columns result, assigned and u_assigned")
                bias = u_bias_pt(
                    pd.to_numeric(rounds["result"], errors="raise"),
                    pd.to_numeric(rounds["assigned"], errors="raise"),
                    pd.to_numeric(rounds["u_assigned"], errors="raise"),
                    relative=relative,
                )
            else:
                bias = u_bias_crm(
                    parse_numbers(crm_text, "Results on the CRM"), certified, u_cert, relative
                )
            td = combine_topdown(urw, bias, k=k_td)
        pct = " %" if relative else ""
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("u(Rw)", f"{td.u_rw:.3g}{pct}")
        m2.metric("u(bias)", f"{td.u_bias:.3g}{pct}")
        m3.metric("u_c (top-down)", f"{td.combined:.3g}{pct}")
        m4.metric(f"U (top-down, k = {td.k:g})", f"{td.expanded:.3g}{pct}")
        if source == "PT rounds" and bias.n < 6:
            st.caption(f"Only {bias.n} PT rounds: Nordtest suggests at least six.")
        st.dataframe(
            td.table.style.format({"u": "{:.3g}", "share_of_variance": "{:.1%}"}),
            hide_index=True, width="stretch",
        )  # fmt: skip
        fig_td = px.bar(
            td.table.iloc[::-1], x="share_of_variance", y="term", orientation="h",
            labels={"share_of_variance": "Share of u_c²", "term": ""},
            title="Where the uncertainty comes from",
        )  # fmt: skip
        fig_td.update_layout(xaxis_tickformat=".0%", height=120 + 40 * len(td.table))
        fig_td.update_traces(marker_color="#2c6e8f")
        st.plotly_chart(fig_td, width="stretch")
        what_this_means(
            explain.topdown(td.table, relative, td.expanded, td.k, "PT" if bias.source == "PT"
                            else "CRM")
        )  # fmt: skip
        st.markdown("**Bias data used**")
        st.dataframe(bias.table, hide_index=True, width="stretch")

    export_header()
    st.download_button(
        "Download top-down table (CSV)", csv_bytes(td.table), "topdown_uncertainty.csv",
        "text/csv", key="td_download",
    )  # fmt: skip
    report_button(
        lambda: RunRecord(
            "labqc.topdown.combine_topdown",
            title="Top-down uncertainty",
            method=(
                "Nordtest TR 537: u(Rw) from the control sample SD"
                + (" combined with s_r from duplicates" if s_r is not None else "")
                + (
                    "; u(bias) = sqrt(RMS_bias^2 + u(Cref)^2) from PT rounds"
                    if bias.source == "PT"
                    else "; u(bias) = sqrt(b^2 + (s/sqrt(n))^2 + u(Cref)^2) from a CRM"
                )
                + f"; u_c = sqrt(u(Rw)^2 + u(bias)^2); U = {td.k:g} u_c."
            ),
            inputs={"control_results": list(qc_values), "bias_data": bias.table},
            settings={"relative": relative, "k": td.k, "bias_source": bias.source},
            result={
                "u_rw": td.u_rw, "u_bias": td.u_bias, "u_c": td.combined, "U": td.expanded,
                "table": td.table,
            },
        ),
        key="td_report",
    )  # fmt: skip

footer()
