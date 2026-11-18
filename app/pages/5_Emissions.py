"""Emissions page: analyser readings -> mg/m3 dry, standard conditions, reference O2."""

import pandas as pd
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

from labqc.emissions import MOLAR_MASS, UNITS, correct_emission

page(
    "Emissions",
    "Flue-gas readings converted to mg/m³ of dry gas at 273.15 K, 101.325 kPa and the "
    "reference O₂. The example is the boiler test from examples/boiler_emissions.py.",
)
FIELDS = ("o2_measured", "o2_ref", "water_vol_fraction", "t_c", "p_kpa")


def load_example() -> None:
    for name in FIELDS:
        st.session_state[f"em_{name}"] = examples()["emissions"][name]
    st.session_state.em_table = demo_table("boiler_readings")
    st.session_state.em_version = st.session_state.get("em_version", 0) + 1


if "em_table" not in st.session_state:
    load_example()

inputs, results = columns()

with inputs:
    st.subheader("Inputs")
    st.button("Load example data", on_click=load_example)
    c1, c2 = st.columns(2)
    o2_measured = c1.number_input("Measured O₂, dry (%)", key="em_o2_measured", format="%.2f")
    o2_ref = c2.number_input("Reference O₂ (%)", key="em_o2_ref", format="%.1f")
    water = c1.number_input(
        "Water vapour (volume fraction)",
        min_value=0.0,
        max_value=0.99,
        key="em_water_vol_fraction",
        format="%.3f",
        help="0 for readings already on a dry basis; 0.12 means 12 % water vapour.",
    )
    st.markdown("Temperature and pressure are used only for readings in *mg/m3 actual*.")
    c1, c2 = st.columns(2)
    t_c = c1.number_input("Gas temperature (°C)", key="em_t_c", format="%.1f")
    p_kpa = c2.number_input("Gas pressure (kPa)", key="em_p_kpa", format="%.3f")
    st.markdown("**Readings** (limit in mg/m³ at the reference O₂, optional)")
    readings = st.data_editor(
        st.session_state.em_table,
        key=f"em_editor_{st.session_state.em_version}",
        num_rows="dynamic",
        width="stretch",
        column_config={
            "gas": st.column_config.SelectboxColumn("gas", options=list(MOLAR_MASS)),
            "unit": st.column_config.SelectboxColumn("unit", options=list(UNITS), default="ppm"),
        },
    )

with results:
    st.subheader("Results")
    with friendly_errors():
        rows = readings.dropna(how="all")
        if rows.empty:
            raise ValueError("Add at least one reading")
        out = []
        for i, r in enumerate(rows.itertuples(), start=1):
            if pd.isna(r.gas) or pd.isna(r.value):
                raise ValueError(f"Row {i}: choose a gas and enter a value")
            limit = None if pd.isna(r.limit) else float(r.limit)
            res = correct_emission(
                float(r.value),
                r.gas,
                "ppm" if pd.isna(r.unit) else r.unit,
                o2_measured=o2_measured,
                o2_ref=o2_ref,
                water_vol_fraction=water,
                t_c=t_c,
                p_kpa=p_kpa,
                limit=limit,
            )
            out.append(
                {
                    "gas": res.gas,
                    "reading": res.value,
                    "unit": res.unit,
                    "mg/m3 as measured": res.mg_m3,
                    "mg/m3 dry": res.mg_m3_dry,
                    f"mg/m3 at {o2_ref:g} % O2": res.mg_m3_ref,
                    "limit": res.limit,
                    "% of limit": res.percent_of_limit,
                    "result": {None: "", True: "pass", False: "FAIL"}[res.passed],
                }
            )
    table = pd.DataFrame(out)
    st.metric(
        "O₂ correction factor",
        f"{res.correction_factor:.3f}",
        help="(20.9 − O₂ ref) / (20.9 − O₂ measured)",
    )
    st.dataframe(
        table.style.format(
            {
                "mg/m3 as measured": "{:.1f}",
                "mg/m3 dry": "{:.1f}",
                f"mg/m3 at {o2_ref:g} % O2": "{:.1f}",
                "limit": "{:.0f}",
                "% of limit": "{:.0f} %",
            },
            na_rep="",
        ),
        hide_index=True,
        width="stretch",
    )
    limited = table.dropna(subset=["% of limit"])
    for _, row in limited.iterrows():
        text = f"{row['gas']}: {row['% of limit']:.0f} % of the limit"
        (st.warning if row["result"] == "FAIL" else st.success)(text)
    if not limited.empty:
        fig = px.bar(
            limited,
            x="gas",
            y="% of limit",
            color="result",
            color_discrete_map={"pass": "#2c6e8f", "FAIL": "#c0392b"},
            title="Corrected result as % of the limit",
        )
        fig.add_hline(y=100, line_dash="dash", line_color="black", annotation_text="limit")
        fig.update_layout(height=320, margin={"t": 40}, showlegend=False)
        st.plotly_chart(fig, width="stretch")
    st.caption(
        "Limits are placeholders unless you enter the ones from your standard and appliance class."
    )

export_header()
st.download_button("Download results (CSV)", csv_bytes(table), "emissions.csv", "text/csv")
footer()
