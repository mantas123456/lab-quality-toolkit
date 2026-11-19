"""Proficiency testing page: z, zeta, En and a round's robust statistics (labqc.proficiency)."""

import explain
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import (
    CLASS_COLOURS,
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
    what_this_means,
)

from labqc.control_charts import Limits
from labqc.proficiency import (
    classify,
    en_number,
    pt_history,
    robust_mean_sd,
    z_score,
    zeta_score,
)
from labqc.report import RunRecord

page(
    "Proficiency testing",
    "Performance scores for one result (ISO 13528) and the robust consensus of a round "
    "(Algorithm A, ISO 13528 Annex C), and your z-scores across rounds.",
)
PAGE = "pages/3_Proficiency_testing.py"
TABS = ["Scores and round", "PT history"]

FIELDS = ("x", "assigned", "sigma_pt", "u_x", "u_assigned", "U_x", "U_assigned")


def load_example() -> None:
    for name in FIELDS:
        st.session_state[f"pt_{name}"] = examples()["pt"][name]
    st.session_state.pt_table = demo_table("pt_round")
    st.session_state.pt_version = st.session_state.get("pt_version", 0) + 1


def load_history() -> None:
    st.session_state.pt_hist_table = demo_table("pt_history")
    st.session_state.pt_hist_version = st.session_state.get("pt_hist_version", 0) + 1


def load_hist_upload() -> None:
    file = st.session_state.get("pt_hist_upload")
    if file is None:
        return
    try:
        st.session_state.pt_hist_table = pd.read_csv(file)
    except Exception:  # any parser problem becomes a plain message below
        st.session_state.pt_hist_upload_error = "Could not read the file as CSV."
        return
    st.session_state.pop("pt_hist_upload_error", None)
    st.session_state.pt_hist_version = st.session_state.get("pt_hist_version", 0) + 1


def open_tab(name: str, loader) -> None:
    loader()
    st.session_state.pt_tab_default = name


deep_link(
    PAGE,
    {
        "pt-round": lambda: open_tab(TABS[0], load_example),
        "pt-history": lambda: open_tab(TABS[1], load_history),
    },
)
if "pt_table" not in st.session_state:
    load_example()
if "pt_hist_table" not in st.session_state:
    load_history()

tab_scores, tab_history = st.tabs(TABS, default=st.session_state.get("pt_tab_default", TABS[0]))

with tab_scores:
    inputs, results = columns()

    with inputs:
        st.subheader("Inputs")
        st.button("Load example data", on_click=load_example)
        st.markdown("**Your result**")
        c1, c2, c3 = st.columns(3)
        x = c1.number_input("Your result x", key="pt_x", format="%.4f")
        assigned = c2.number_input("Assigned value", key="pt_assigned", format="%.4f")
        sigma_pt = c3.number_input("σ_pt", key="pt_sigma_pt", format="%.4f")
        c1, c2 = st.columns(2)
        u_x = c1.number_input("u(x), standard", key="pt_u_x", format="%.4f")
        u_assigned = c2.number_input("u(assigned), standard", key="pt_u_assigned", format="%.4f")
        U_x = c1.number_input("U(x), expanded", key="pt_U_x", format="%.4f")
        U_assigned = c2.number_input("U(assigned), expanded", key="pt_U_assigned", format="%.4f")
        st.markdown("**All results of the round** (columns lab, result)")
        round_table = st.data_editor(
            st.session_state.pt_table,
            key=f"pt_editor_{st.session_state.pt_version}",
            num_rows="dynamic",
            width="stretch",
            height=300,
        )

    def badge(label: str) -> str:
        return f":{CLASS_COLOURS[label]}[**{label}**]"

    with results:
        st.subheader("Scores for your result")
        with friendly_errors():
            if sigma_pt <= 0:
                raise ValueError("σ_pt must be greater than 0")
            if u_x == 0 and u_assigned == 0:
                raise ValueError("zeta needs u(x) or u(assigned) greater than 0")
            if U_x == 0 and U_assigned == 0:
                raise ValueError("En needs U(x) or U(assigned) greater than 0")
            z = z_score(x, assigned, sigma_pt)
            zeta = zeta_score(x, assigned, u_x, u_assigned)
            en = en_number(x, assigned, U_x, U_assigned)
        scores = pd.DataFrame(
            {
                "score": ["z", "zeta", "En"],
                "value": [z, zeta, en],
                "status": [classify(z), classify(zeta), classify(en, "en")],
            }
        )
        for col, row in zip(st.columns(3), scores.itertuples(), strict=True):
            col.metric(row.score, f"{row.value:.2f}")
            col.markdown(badge(row.status))
        st.caption(
            "z and zeta: |score| ≤ 2 satisfactory, 2–3 questionable, ≥ 3 unsatisfactory. "
            "En: |En| ≤ 1 satisfactory."
        )
        what_this_means(explain.pt_scores(z, classify(z), en, classify(en, "en")))

        st.subheader("The round")
        with friendly_errors():
            data = round_table.dropna(how="all")
            if "result" not in data.columns:
                raise ValueError("The round table needs a column named result")
            values = pd.to_numeric(data["result"], errors="raise")
            if len(values) < 3:
                raise ValueError("A round needs at least three results")
            mean, sd = robust_mean_sd(values)
            if sd == 0:
                raise ValueError("All results are identical, so the robust SD is 0")
        labs = data["lab"] if "lab" in data.columns else pd.Series(range(1, len(values) + 1))
        round_z = [z_score(v, mean, sd) for v in values]
        round_out = pd.DataFrame(
            {
                "lab": labs.astype(str).to_numpy(),
                "result": values.to_numpy(),
                "z (robust)": round_z,
                "status": [classify(v) for v in round_z],
            }
        )
        m1, m2, m3 = st.columns(3)
        m1.metric("Robust mean", f"{mean:.4g}")
        m2.metric("Robust SD", f"{sd:.3g}")
        m3.metric("Labs", len(values))

        limits = Limits(mean, sd)
        ordered = round_out.sort_values("result")
        fig = go.Figure(
            go.Scatter(
                x=ordered["lab"],
                y=ordered["result"],
                mode="markers",
                marker={"size": 10, "color": [CLASS_COLOURS[s] for s in ordered["status"]]},
                name="Results",
            )
        )
        for n, dash in [(0, "solid"), (2, "dash"), (-2, "dash"), (3, "dot"), (-3, "dot")]:
            fig.add_hline(y=limits.line(n), line_dash=dash, line_width=1, line_color="grey")
        fig.update_layout(
            height=340,
            margin={"t": 30},
            yaxis_title="Result",
            title="Results with robust mean ± 2 and 3 SD",
        )
        st.plotly_chart(fig, width="stretch")
        what_this_means(explain.pt_round(round_out, mean, sd))
        st.dataframe(
            round_out.style.format({"result": "{:.4g}", "z (robust)": "{:.2f}"}),
            hide_index=True,
            width="stretch",
        )

    export_header()
    c1, c2 = st.columns(2)
    c1.download_button("Download scores (CSV)", csv_bytes(scores), "pt_scores.csv", "text/csv")
    c2.download_button("Download round (CSV)", csv_bytes(round_out), "pt_round.csv", "text/csv")
    report_button(
        lambda: RunRecord(
            "labqc.proficiency",
            title="Proficiency testing",
            method=(
                "z = (x - X) / sigma_pt, zeta = (x - X) / sqrt(u_x^2 + u_X^2), "
                "En = (x - X) / sqrt(U_x^2 + U_X^2) (ISO 13528); robust mean and SD of the "
                "round by Algorithm A (ISO 13528 Annex C), with z of each lab against them."
            ),
            inputs={
                "x": x, "assigned": assigned, "sigma_pt": sigma_pt, "u_x": u_x,
                "u_assigned": u_assigned, "U_x": U_x, "U_assigned": U_assigned,
                "round": round_out[["lab", "result"]],
            },
            result={
                "scores": scores, "robust_mean": mean, "robust_sd": sd,
                "round_scores": round_out,
            },
        )
    )  # fmt: skip


def signal_text(two: bool, trend: bool) -> str:
    return ", ".join(n for n, f in (("two beyond 2", two), ("nine on one side", trend)) if f)


with tab_history:
    inputs, results = columns()
    with inputs:
        st.subheader("Inputs")
        st.button("Load example history", on_click=load_history)
        st.markdown("**Your z-scores, one row per round** (columns date, z)")
        hist_table = st.data_editor(
            st.session_state.pt_hist_table,
            key=f"pt_hist_editor_{st.session_state.pt_hist_version}",
            num_rows="dynamic",
            width="stretch",
            height=400,
        )
        st.file_uploader(
            "Or upload a CSV with columns date and z",
            type="csv",
            key="pt_hist_upload",
            on_change=load_hist_upload,
        )
        if "pt_hist_upload_error" in st.session_state:
            st.error(st.session_state.pt_hist_upload_error)

    with results:
        st.subheader("z-scores over rounds")
        with friendly_errors():
            if not {"date", "z"} <= set(hist_table.columns):
                raise ValueError("The history table needs columns date and z")
            hist_in = hist_table.dropna(how="all").copy()
            hist_in["z"] = pd.to_numeric(hist_in["z"], errors="raise")
            hist_in["date"] = hist_in["date"].astype(str)
            if len(hist_in) < 2:
                raise ValueError("PT history needs at least two rounds")
            history = pt_history(hist_in)
        m1, m2, m3 = st.columns(3)
        m1.metric("Rounds", len(history))
        m2.metric("Unsatisfactory", int((history["classification"] == "unsatisfactory").sum()))
        m3.metric("Rounds needing action", int(history["action"].sum()))
        fig_h = go.Figure(
            go.Scatter(
                x=history["date"], y=history["z"], mode="lines+markers", name="z",
                line={"color": "#bbb", "width": 1},
                marker={"size": 10, "color": [CLASS_COLOURS[c] for c in history["classification"]]},
            )
        )  # fmt: skip
        flagged_h = history[history["two_beyond_2"] | history["trend_9"]]
        fig_h.add_trace(
            go.Scatter(
                x=flagged_h["date"], y=flagged_h["z"], mode="markers", name="Warning signal",
                marker={"size": 18, "color": "rgba(0,0,0,0)",
                        "line": {"color": "black", "width": 2}},
                text=[signal_text(a, b) for a, b in
                      zip(flagged_h["two_beyond_2"], flagged_h["trend_9"], strict=True)],
                hovertemplate="%{x}: z = %{y}<br>%{text}<extra></extra>",
            )
        )  # fmt: skip
        for n_sd, dash in [(0, "solid"), (2, "dash"), (-2, "dash"), (3, "solid"), (-3, "solid")]:
            fig_h.add_hline(
                y=n_sd, line_dash=dash, line_width=1,
                line_color="black" if abs(n_sd) == 3 else "grey",
            )  # fmt: skip
        fig_h.update_layout(
            height=380, margin={"t": 30}, xaxis_title="Round", yaxis_title="z",
            legend={"orientation": "h", "y": 1.1},
        )  # fmt: skip
        st.plotly_chart(fig_h, width="stretch")
        what_this_means(explain.pt_history(history))
        st.dataframe(history, hide_index=True, width="stretch")
        st.caption(
            "Signals: |z| > 2 in two rounds in a row, and nine rounds in a row on one side of "
            "zero (Nelson rule 2). Circled points carry a signal."
        )

    export_header()
    st.download_button(
        "Download PT history (CSV)", csv_bytes(history), "pt_history.csv", "text/csv"
    )
    report_button(
        lambda: RunRecord(
            "labqc.proficiency.pt_history",
            title="PT history",
            method=(
                "z-scores across PT rounds: classification by |z| (ISO 13528), warning signals "
                "for |z| > 2 in two successive rounds and nine successive rounds on one side "
                "of zero."
            ),
            inputs={"rounds": hist_in[["date", "z"]]},
            result={"history": history, "rounds_needing_action": int(history["action"].sum())},
        ),
        key="pt_hist_report",
    )

footer()
