"""Method validation page: calibration, LOD/LOQ, precision, recovery (labqc.validation)."""

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
    parse_numbers,
    remember,
    report_button,
    what_this_means,
)
from plotly.subplots import make_subplots

from labqc.report import RunRecord
from labqc.validation import linearity, lod_loq, precision, recovery

page(
    "Method validation",
    "Calibration linearity (ordinary or weighted least squares) with a lack-of-fit test, "
    "LOD/LOQ (ICH Q2), precision and spike recovery.",
)


def load_example() -> None:
    ex = examples()["validation"]
    st.session_state.val_table = demo_table("calibration")
    st.session_state.val_weights = "none"
    st.session_state.val_blank_sd = 0.0
    st.session_state.val_replicates = ", ".join(str(v) for v in ex["replicates"])
    st.session_state.val_measured = ex["recovery"]["measured"]
    st.session_state.val_unspiked = ex["recovery"]["unspiked"]
    st.session_state.val_added = ex["recovery"]["added"]
    st.session_state.val_version = st.session_state.get("val_version", 0) + 1


deep_link("pages/2_Method_validation.py", {"calibration": load_example})
if "val_table" not in st.session_state:
    load_example()

inputs, results = columns()

with inputs:
    st.subheader("Inputs")
    st.button("Load example data", on_click=load_example)
    st.markdown("**Calibration** (repeat a concentration for replicates)")
    cal_table = st.data_editor(
        st.session_state.val_table,
        key=f"val_editor_{st.session_state.val_version}",
        num_rows="dynamic",
        width="stretch",
    )
    remember("val_table", cal_table)
    c1, c2 = st.columns(2)
    weights = c1.selectbox("Weighting", ["none", "1/x", "1/x^2"], key="val_weights")
    blank_sd = c2.number_input(
        "Blank SD for LOD/LOQ (0 = residual SD)", min_value=0.0, key="val_blank_sd", format="%.4f"
    )
    st.markdown("**Precision**")
    replicates_text = st.text_area("Replicate results", key="val_replicates", height=70)
    st.markdown("**Spike recovery**")
    c1, c2, c3 = st.columns(3)
    measured = c1.number_input("Spiked result", key="val_measured")
    unspiked = c2.number_input("Unspiked result", key="val_unspiked")
    added = c3.number_input("Amount added", key="val_added")

with results:
    st.subheader("Results")
    with friendly_errors():
        data = cal_table.dropna(how="all")
        if not {"concentration", "signal"} <= set(data.columns):
            raise ValueError("The calibration table needs columns concentration and signal")
        x = pd.to_numeric(data["concentration"], errors="raise")
        sig = pd.to_numeric(data["signal"], errors="raise")
        cal = linearity(x, sig, weights=None if weights == "none" else weights)
        lod, loq = lod_loq(cal, blank_sd or None)
        replicates = parse_numbers(replicates_text, "Replicate results")
        prec = precision(replicates)
        if prec["n"] < 2:
            raise ValueError("Precision needs at least two replicate results")
        if added == 0:
            raise ValueError("Recovery needs an amount added greater than 0")
        rec = recovery(measured, unspiked, added)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Slope", f"{cal.slope:.4g}")
    m2.metric("Intercept", f"{cal.intercept:.3g}")
    m3.metric("R²", f"{cal.r_squared:.5f}")
    m4.metric("Residual SD", f"{cal.residual_sd:.3g}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("LOD", f"{lod:.3g}")
    m2.metric("LOQ", f"{loq:.3g}")
    if cal.lack_of_fit is None:
        m3.metric("Lack of fit", "n/a", help="Needs replicate standards")
    else:
        m3.metric(
            "Lack-of-fit p",
            f"{cal.lack_of_fit.p_value:.3f}",
            delta="line not adequate" if cal.lack_of_fit.significant else "line adequate",
            delta_color="inverse" if cal.lack_of_fit.significant else "normal",
        )
    m4.metric("Weighting", cal.weighting)

    ends = [x.min(), x.max()]
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.68, 0.32], vertical_spacing=0.06
    )
    fig.add_trace(go.Scatter(x=x, y=sig, mode="markers", name="Standards"), row=1, col=1)
    fig.add_trace(
        go.Scatter(x=ends, y=cal.predict_signal(ends), mode="lines", name="Fitted line"),
        row=1,
        col=1,
    )
    fig.add_trace(go.Scatter(x=x, y=cal.residuals, mode="markers", name="Residuals"), row=2, col=1)
    fig.add_hline(y=0, line_width=1, line_color="grey", row=2, col=1)
    fig.update_yaxes(title_text="Signal", row=1, col=1)
    fig.update_yaxes(title_text="Residual", row=2, col=1)
    fig.update_xaxes(title_text="Concentration", row=2, col=1)
    fig.update_layout(height=460, margin={"t": 30}, legend={"orientation": "h", "y": 1.08})
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Residuals should scatter evenly around zero; a curve or a funnel shape "
        "points to non-linearity or the need for weighting."
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Replicates", prec["n"])
    m2.metric("Mean", f"{prec['mean']:.4g}")
    m3.metric("RSD", f"{prec['rsd_percent']:.2f} %")
    m4.metric("Recovery", f"{rec:.1f} %")
    what_this_means(
        explain.validation(
            cal.r_squared,
            None if cal.lack_of_fit is None else cal.lack_of_fit.p_value,
            None if cal.lack_of_fit is None else cal.lack_of_fit.significant,
            lod,
            loq,
            rec,
        )
    )

export_header()
summary = pd.DataFrame(
    {
        "quantity": [
            "slope", "intercept", "r_squared", "residual_sd", "weighting", "lod", "loq",
            "lack_of_fit_p", "precision_n", "precision_mean", "precision_sd", "rsd_percent",
            "recovery_percent",
        ],
        "value": [
            cal.slope, cal.intercept, cal.r_squared, cal.residual_sd, cal.weighting, lod, loq,
            None if cal.lack_of_fit is None else cal.lack_of_fit.p_value, prec["n"],
            prec["mean"], prec["sd"], prec["rsd_percent"], rec,
        ],
    }
)  # fmt: skip
residuals = pd.DataFrame({"concentration": x, "signal": sig, "residual": cal.residuals})
c1, c2 = st.columns(2)
c1.download_button("Download results (CSV)", csv_bytes(summary), "validation.csv", "text/csv")
c2.download_button(
    "Download residuals (CSV)", csv_bytes(residuals), "calibration_residuals.csv", "text/csv"
)
report_button(
    lambda: RunRecord(
        "labqc.validation",
        title="Method validation",
        method=(
            f"Least-squares calibration line (weighting {cal.weighting}) with a lack-of-fit "
            "F-test from replicate standards; LOD = 3.3 s / slope and LOQ = 10 s / slope "
            "(ICH Q2); precision as sample SD and RSD; recovery = 100 (spiked - unspiked) / added."
        ),
        inputs={
            "calibration": residuals[["concentration", "signal"]],
            "replicates": replicates,
            "recovery": {"spiked": measured, "unspiked": unspiked, "added": added},
        },
        settings={"weighting": weights, "blank_sd": blank_sd or None},
        result=dict(zip(summary["quantity"], summary["value"], strict=True)),
    )
)
footer()
