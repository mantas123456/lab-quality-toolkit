"""QC charts page: Westgard (one or several control levels), CUSUM and EWMA
(labqc.control_charts)."""

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
    examples,
    export_header,
    footer,
    friendly_errors,
    page,
    report_button,
    tabs,
    what_this_means,
)

from labqc.control_charts import (
    REJECT_RULES,
    Limits,
    cusum,
    ewma,
    limits_from_data,
    westgard,
    westgard_levels,
)
from labqc.report import RunRecord

PAGE = "pages/4_QC_charts.py"
TABS = ["Westgard", "CUSUM", "EWMA"]
RULES = ("1_2s", *REJECT_RULES)

page(
    "QC charts",
    "Daily control results on a Levey-Jennings chart with the Westgard multirules (one "
    "control level or several run together), and CUSUM and EWMA charts for small shifts. "
    "The example is examples/westgard_iqc.py: a +1.4 mg/kg shift from day 45.",
)


def _common_settings(table: str, tab: str, across: bool) -> None:
    st.session_state.qc_table = demo_table(table)
    st.session_state.qc_mode = "From the first results"
    st.session_state.qc_baseline = examples()["qc"]["baseline_points"]
    st.session_state.qc_method = "sd"
    st.session_state.qc_centre = 50.0
    st.session_state.qc_sd = 1.0
    st.session_state.qc_across = across
    st.session_state.qc_tab_default = tab
    st.session_state.pop("qc_level", None)


def load_example() -> None:
    _common_settings("qc_daily", st.session_state.get("qc_tab_default", "Westgard"), False)


def load_upload() -> None:
    file = st.session_state.get("qc_upload")
    if file is None:
        return
    try:
        st.session_state.qc_table = pd.read_csv(file)
        st.session_state.pop("qc_upload_error", None)
        st.session_state.pop("qc_level", None)
    except Exception:  # any parser problem becomes a plain message below
        st.session_state.qc_upload_error = "Could not read the file as CSV."


deep_link(
    PAGE,
    {
        "westgard": lambda: _common_settings("qc_daily", "Westgard", False),
        "westgard-levels": lambda: _common_settings("qc_levels", "Westgard", True),
        "cusum": lambda: _common_settings("qc_daily", "CUSUM", False),
        "ewma": lambda: _common_settings("qc_daily", "EWMA", False),
    },
)
if "qc_table" not in st.session_state:
    load_example()
st.session_state.setdefault("qc_cusum_k", 0.5)
st.session_state.setdefault("qc_cusum_h", 5.0)
st.session_state.setdefault("qc_ewma_lam", 0.2)
st.session_state.setdefault("qc_ewma_L", 3.0)

inputs, results = columns()

with inputs:
    st.subheader("Inputs")
    st.button("Load example data", on_click=load_example)
    st.file_uploader(
        "Upload a CSV with a value column (optionally day or date, and level for several "
        "control materials)",
        type="csv",
        key="qc_upload",
        on_change=load_upload,
    )
    if "qc_upload_error" in st.session_state:
        st.error(st.session_state.qc_upload_error)
    data = st.session_state.qc_table
    levels = list(dict.fromkeys(data["level"].dropna().astype(str))) if "level" in data else []
    if levels:
        level = st.selectbox(
            "Control level for single-level charts", levels, key="qc_level",
            help="CUSUM, EWMA and the one-level Westgard chart use this level.",
        )  # fmt: skip
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
    st.dataframe(data, height=260, width="stretch", hide_index=True)


def series_and_limits(values, x):
    """Baseline count and limits for one series, as chosen in the inputs."""
    if mode == "From the first results":
        n = int(n_base)
        if n >= len(values):
            raise ValueError("Leave at least one result after the baseline to check")
        lim = limits_from_data(values[:n], method=method)
    else:
        if sd_in <= 0:
            raise ValueError("SD must be greater than 0")
        n = 0
        lim = Limits(centre, sd_in)
    if lim.sd <= 0:
        raise ValueError("The baseline SD is 0: the baseline results are all identical")
    return n, lim


with results:
    st.subheader("Results")
    with friendly_errors():
        if "value" not in data.columns:
            raise ValueError("The CSV needs a column named value")
        single = data[data["level"].astype(str) == level] if levels else data
        values = pd.to_numeric(single["value"], errors="raise").to_numpy()
        x_col = next((c for c in ("day", "date", "run") if c in data.columns), None)
        x_name = x_col or "run"
        x = single[x_col].to_numpy() if x_col else list(range(1, len(values) + 1))
        n_base, limits = series_and_limits(values, x)

    tab_w, tab_c, tab_e = tabs(TABS, default=st.session_state.get("qc_tab_default", TABS[0]))

    # --- Westgard ------------------------------------------------------------------------
    with tab_w:
        across = False
        if len(levels) in (2, 3):
            across = st.checkbox(
                f"Apply the rules across the {len(levels)} levels run together",
                key="qc_across",
            )
        elif levels:
            st.caption("Rules across levels need two or three control levels.")
        if across:
            with friendly_errors():
                if mode != "From the first results":
                    raise ValueError(
                        "Across levels, the limits come from the first results of each level: "
                        "choose 'From the first results'"
                    )
                if not x_col:
                    raise ValueError("Across levels, the CSV needs a day, date or run column")
                wide = data.pivot_table(
                    index=x_col, columns="level", values="value", aggfunc="first", sort=False
                )[levels].dropna()
                n = int(n_base)
                if n >= len(wide):
                    raise ValueError("Leave at least one run after the baseline to check")
                lims = {lv: limits_from_data(wide[lv].to_numpy()[:n], method) for lv in levels}
                if any(lim.sd <= 0 for lim in lims.values()):
                    raise ValueError("A level's baseline SD is 0: its results are all identical")
                table = westgard_levels({lv: wide[lv].to_numpy()[n:] for lv in levels}, lims)
            rule_cols = [c for c in table.columns if not c.startswith("z_") and c != "status"]
            table.insert(0, x_name, wide.index[n:])
            table["rules"] = table[rule_cols].apply(lambda r: ", ".join(r.index[r]), axis=1)
            rules_used = tuple(rule_cols)
            fig = go.Figure()
            for i, lv in enumerate(levels):
                fig.add_trace(
                    go.Scatter(
                        x=table[x_name], y=table[f"z_{lv}"], mode="lines+markers", name=lv,
                        line={"width": 1, "dash": "solid" if i == 0 else "dot"},
                        marker={"size": 8, "color": [STATUS_COLOURS[s] for s in table["status"]],
                                "symbol": ["circle", "square", "diamond"][i]},
                        text=table["rules"],
                        hovertemplate="%{x}: z = %{y}<br>%{text}<extra></extra>",
                    )
                )  # fmt: skip
            for n_sd in (0, 1, -1, 2, -2, 3, -3):
                fig.add_hline(
                    y=n_sd, line_width=1, line_color="black" if abs(n_sd) == 3 else "grey",
                    line_dash={0: "solid", 1: "dot", 2: "dash", 3: "solid"}[abs(n_sd)],
                )  # fmt: skip
            fig.update_layout(
                height=420, margin={"t": 30}, xaxis_title=x_name,
                yaxis_title="z (SD from each level's centre)",
                legend={"orientation": "h", "y": 1.08},
            )  # fmt: skip
            counts = table["status"].value_counts()
            m1, m2, m3 = st.columns(3)
            m1.metric("Levels", len(levels))
            m2.metric("Warnings", int(counts.get("warning", 0)))
            m3.metric("Rejects", int(counts.get("reject", 0)))
            st.plotly_chart(fig, width="stretch")
            shown = [x_name, *[f"z_{lv}" for lv in levels], "status", "rules"]
        else:
            with friendly_errors():
                table = westgard(values[n_base:], limits)
            table.insert(0, x_name, x[n_base:])
            table["rules"] = table[list(RULES)].apply(lambda r: ", ".join(r.index[r]), axis=1)
            rules_used = RULES
            counts = table["status"].value_counts()
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Centre", f"{limits.centre:.4g}")
            m2.metric("SD", f"{limits.sd:.3g}")
            m3.metric("Warnings", int(counts.get("warning", 0)))
            m4.metric("Rejects", int(counts.get("reject", 0)))

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=x, y=values, mode="lines", line={"color": "#bbb", "width": 1},
                    showlegend=False,
                )
            )  # fmt: skip
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
                        x=part.iloc[:, 0], y=part["value"], mode="markers",
                        name=status.capitalize(), marker={"color": colour, "size": 9},
                        text=part["rules"], hovertemplate="%{x}: %{y}<br>%{text}<extra></extra>",
                    )
                )  # fmt: skip
            for n_sd, dash in [(0, "solid"), (1, "dot"), (-1, "dot"), (2, "dash"), (-2, "dash"),
                               (3, "solid"), (-3, "solid")]:  # fmt: skip
                fig.add_hline(
                    y=limits.line(n_sd), line_dash=dash, line_width=1,
                    line_color="black" if abs(n_sd) == 3 else "grey",
                    annotation_text=f"{n_sd:+d} SD" if n_sd else "centre",
                    annotation_position="right",
                )  # fmt: skip
            fig.update_layout(
                height=420, margin={"t": 30, "r": 60}, xaxis_title=x_name,
                yaxis_title="Control result", legend={"orientation": "h", "y": 1.08},
            )  # fmt: skip
            st.plotly_chart(fig, width="stretch")
            shown = [x_name, "value", "z", "status", "rules"]

        flagged = table[table["status"] != "accept"]
        what_this_means(explain.westgard(table, x_name, rules_used))
        if not flagged.empty:
            st.markdown("**Flagged results**")
            st.dataframe(flagged[shown], hide_index=True, width="stretch")
            st.caption(
                "1_2s alone is a warning. 1_3s and R_4s point to random error; "
                "2_2s, 2of3_2s, 3_1s, 4_1s, 10_x and 12_x to systematic error such as "
                "calibration."
            )

    # --- CUSUM ---------------------------------------------------------------------------
    with tab_c:
        c1, c2 = st.columns(2)
        k_ref = c1.number_input(
            "k, reference value (SD)", min_value=0.0, step=0.1, key="qc_cusum_k",
            help="Half the shift to detect, in SD; 0.5 for a 1 SD shift.",
        )  # fmt: skip
        h = c2.number_input("h, decision interval (SD)", min_value=0.1, step=0.5, key="qc_cusum_h")
        cu = cusum(values[n_base:], limits.centre, limits.sd, k=k_ref, h=h)
        cu.insert(0, x_name, x[n_base:])
        hits = cu[cu["signal"]]
        m1, m2 = st.columns(2)
        m1.metric("Signals", len(hits))
        m2.metric(f"First signal ({x_name})", str(hits.iloc[0, 0]) if len(hits) else "none")
        fig_c = go.Figure()
        fig_c.add_trace(
            go.Scatter(x=cu[x_name], y=cu["c_plus"], mode="lines+markers", name="C+",
                       line={"color": "#2c6e8f"})
        )  # fmt: skip
        fig_c.add_trace(
            go.Scatter(x=cu[x_name], y=-cu["c_minus"], mode="lines+markers", name="−C−",
                       line={"color": "#7a5195"})
        )  # fmt: skip
        fig_c.add_trace(
            go.Scatter(x=hits[x_name],
                       y=hits["c_plus"].where(hits["signal_high"], -hits["c_minus"]),
                       mode="markers", name="Signal",
                       marker={"color": STATUS_COLOURS["reject"], "size": 11, "symbol": "x"})
        )  # fmt: skip
        for y_line in (h, -h):
            fig_c.add_hline(y=y_line, line_dash="dash", line_color="black", line_width=1)
        fig_c.add_hline(y=0, line_color="grey", line_width=1)
        fig_c.update_layout(
            height=380, margin={"t": 30}, xaxis_title=x_name,
            yaxis_title="Cumulative sum (SD)", legend={"orientation": "h", "y": 1.1},
        )  # fmt: skip
        st.plotly_chart(fig_c, width="stretch")
        what_this_means(explain.cusum(cu, x_name, h))
        st.caption(
            f"Tabular CUSUM (Montgomery) on z = (x − {limits.centre:.4g}) / {limits.sd:.3g}; "
            "C− is drawn below zero."
        )

    # --- EWMA ----------------------------------------------------------------------------
    with tab_e:
        c1, c2 = st.columns(2)
        lam = c1.number_input(
            "λ, weight of the newest result", min_value=0.01, max_value=1.0, step=0.05,
            key="qc_ewma_lam",
        )  # fmt: skip
        L = c2.number_input("L, limit width (SD)", min_value=0.5, step=0.1, key="qc_ewma_L")
        ew = ewma(values[n_base:], limits.centre, limits.sd, lam=lam, L=L)
        ew.insert(0, x_name, x[n_base:])
        hits_e = ew[ew["signal"]]
        m1, m2 = st.columns(2)
        m1.metric("Points outside", len(hits_e))
        m2.metric(f"First signal ({x_name})", str(hits_e.iloc[0, 0]) if len(hits_e) else "none")
        fig_e = go.Figure()
        fig_e.add_trace(
            go.Scatter(x=ew[x_name], y=ew["value"], mode="markers", name="Result",
                       marker={"color": "#bbb", "size": 6})
        )  # fmt: skip
        fig_e.add_trace(
            go.Scatter(x=ew[x_name], y=ew["ewma"], mode="lines+markers", name="EWMA",
                       line={"color": "#2c6e8f"})
        )  # fmt: skip
        for col, name in (("ucl", "UCL"), ("lcl", "LCL")):
            fig_e.add_trace(
                go.Scatter(x=ew[x_name], y=ew[col], mode="lines", name=name,
                           line={"color": "black", "dash": "dash", "width": 1, "shape": "hv"})
            )  # fmt: skip
        fig_e.add_trace(
            go.Scatter(x=hits_e[x_name], y=hits_e["ewma"], mode="markers", name="Signal",
                       marker={"color": STATUS_COLOURS["reject"], "size": 11, "symbol": "x"})
        )  # fmt: skip
        fig_e.add_hline(y=limits.centre, line_color="grey", line_width=1)
        fig_e.update_layout(
            height=380, margin={"t": 30}, xaxis_title=x_name, yaxis_title="Control result",
            legend={"orientation": "h", "y": 1.1},
        )  # fmt: skip
        st.plotly_chart(fig_e, width="stretch")
        what_this_means(explain.ewma(ew, x_name, lam))

export_header()
c1, c2, c3 = st.columns(3)
c1.download_button(
    "Download Westgard status (CSV)", csv_bytes(table), "westgard_status.csv", "text/csv"
)
c2.download_button("Download CUSUM (CSV)", csv_bytes(cu), "cusum.csv", "text/csv")
c3.download_button("Download EWMA (CSV)", csv_bytes(ew), "ewma.csv", "text/csv")
report_button(
    lambda: RunRecord(
        "labqc.control_charts.westgard_levels" if across else "labqc.control_charts.westgard",
        title="QC chart" + (f" ({len(levels)} levels)" if across else ""),
        method=(
            "Westgard multirules across control levels on z per level"
            if across
            else "Levey-Jennings chart; Westgard multirules 1_2s (warning), 1_3s, 2_2s, R_4s, "
            "4_1s and 10_x (reject) on z = (x - centre) / SD."
        )
        + f" CUSUM k = {k_ref:g}, h = {h:g}; EWMA lambda = {lam:g}, L = {L:g} "
        "(Montgomery).",
        inputs={"results": data},
        settings={
            "limits": mode,
            "baseline_results": n_base,
            "sd_from": method if n_base else None,
            "level": level if levels else None,
            "across_levels": across,
        },
        result={
            "centre": limits.centre,
            "sd": limits.sd,
            "warnings": int(counts.get("warning", 0)),
            "rejects": int(counts.get("reject", 0)),
            "flagged": flagged[shown],
            "cusum_signals": int(cu["signal"].sum()),
            "ewma_signals": int(ew["signal"].sum()),
        },
    )
)
footer()
