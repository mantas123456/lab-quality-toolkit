"""Proficiency testing page: z, zeta, En and a round's robust statistics (labqc.proficiency)."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import (
    CLASS_COLOURS,
    columns,
    csv_bytes,
    demo_table,
    examples,
    export_header,
    footer,
    friendly_errors,
    page,
)

from labqc.control_charts import Limits
from labqc.proficiency import classify, en_number, robust_mean_sd, z_score, zeta_score

page(
    "Proficiency testing",
    "Performance scores for one result (ISO 13528) and the robust consensus of a round "
    "(Algorithm A, ISO 13528 Annex C).",
)

FIELDS = ("x", "assigned", "sigma_pt", "u_x", "u_assigned", "U_x", "U_assigned")


def load_example() -> None:
    for name in FIELDS:
        st.session_state[f"pt_{name}"] = examples()["pt"][name]
    st.session_state.pt_table = demo_table("pt_round")
    st.session_state.pt_version = st.session_state.get("pt_version", 0) + 1


if "pt_table" not in st.session_state:
    load_example()

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
    st.dataframe(
        round_out.style.format({"result": "{:.4g}", "z (robust)": "{:.2f}"}),
        hide_index=True,
        width="stretch",
    )

export_header()
c1, c2 = st.columns(2)
c1.download_button("Download scores (CSV)", csv_bytes(scores), "pt_scores.csv", "text/csv")
c2.download_button("Download round (CSV)", csv_bytes(round_out), "pt_round.csv", "text/csv")
footer()
