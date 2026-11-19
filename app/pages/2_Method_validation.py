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
    tabs,
    what_this_means,
)
from plotly.subplots import make_subplots

from labqc.comparison import bland_altman, deming, passing_bablok
from labqc.outliers import cochran, grubbs, grubbs_two
from labqc.report import RunRecord
from labqc.validation import inverse_prediction, linearity, lod_loq, precision, recovery

page(
    "Method validation",
    "Calibration linearity (ordinary or weighted least squares) with a lack-of-fit test, "
    "LOD/LOQ (ICH Q2), precision, spike recovery and a sample read back from the line; "
    "outlier tests (ISO 5725-2) and method comparison (Bland-Altman, Passing-Bablok, Deming).",
)
PAGE = "pages/2_Method_validation.py"
TABS = ["Calibration and precision", "Outlier tests", "Method comparison"]


def load_example() -> None:
    ex = examples()["validation"]
    st.session_state.val_table = demo_table("calibration")
    st.session_state.val_weights = "none"
    st.session_state.val_blank_sd = 0.0
    st.session_state.val_replicates = ", ".join(str(v) for v in ex["replicates"])
    st.session_state.val_measured = ex["recovery"]["measured"]
    st.session_state.val_unspiked = ex["recovery"]["unspiked"]
    st.session_state.val_added = ex["recovery"]["added"]
    st.session_state.val_samples = ", ".join(str(v) for v in ex["sample_signals"])
    st.session_state.val_version = st.session_state.get("val_version", 0) + 1


def load_outliers() -> None:
    st.session_state.ol_values = ", ".join(str(v) for v in examples()["outliers"]["values"])
    st.session_state.ol_groups = demo_table("outliers_duplicates")
    st.session_state.ol_version = st.session_state.get("ol_version", 0) + 1


def load_comparison() -> None:
    st.session_state.cmp_table = demo_table("comparison")
    st.session_state.cmp_x = "old"
    st.session_state.cmp_y = "new"
    st.session_state.cmp_method = "Passing-Bablok"
    st.session_state.cmp_ratio = 1.0
    st.session_state.cmp_version = st.session_state.get("cmp_version", 0) + 1


def open_tab(name: str, loader) -> None:
    loader()
    st.session_state.val_tab_default = name


deep_link(
    PAGE,
    {
        "calibration": lambda: open_tab(TABS[0], load_example),
        "outliers": lambda: open_tab(TABS[1], load_outliers),
        "method-comparison": lambda: open_tab(TABS[2], load_comparison),
    },
)
if "val_table" not in st.session_state:
    load_example()
if "ol_groups" not in st.session_state:
    load_outliers()
if "cmp_table" not in st.session_state:
    load_comparison()
st.session_state.setdefault("val_samples", "")

tab_cal, tab_outliers, tab_compare = tabs(
    TABS, default=st.session_state.get("val_tab_default", TABS[0])
)

with tab_cal:
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
            "Blank SD for LOD/LOQ (0 = residual SD)",
            min_value=0.0,
            key="val_blank_sd",
            format="%.4f",
        )
        st.markdown("**Precision**")
        replicates_text = st.text_area("Replicate results", key="val_replicates", height=70)
        st.markdown("**Spike recovery**")
        c1, c2, c3 = st.columns(3)
        measured = c1.number_input("Spiked result", key="val_measured")
        unspiked = c2.number_input("Unspiked result", key="val_unspiked")
        added = c3.number_input("Amount added", key="val_added")
        st.markdown("**Sample** (signal readings, to read back a concentration)")
        samples_text = st.text_input("Sample signal readings", key="val_samples")

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
        fig.add_trace(
            go.Scatter(x=x, y=cal.residuals, mode="markers", name="Residuals"), row=2, col=1
        )
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
        sample = None
        if samples_text.strip():
            if cal.weighting != "none":
                st.caption("Reading a sample back from the line needs an unweighted line here.")
            else:
                with friendly_errors():
                    sample = inverse_prediction(cal, parse_numbers(samples_text, "Sample readings"))
                lo, hi = sample.interval()
                m1, m2, m3 = st.columns(3)
                m1.metric("Sample concentration x0", f"{sample.x0:.4g}")
                m2.metric(
                    "u(x0)", f"{sample.u_x0:.3g}", help=f"{sample.m} reading(s), {sample.dof} dof"
                )
                m3.metric("95 % interval", f"{lo:.4g} to {hi:.4g}")
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
                "(ICH Q2); precision as sample SD and RSD; "
                "recovery = 100 (spiked - unspiked) / added."
            ),
            inputs={
                "calibration": residuals[["concentration", "signal"]],
                "replicates": replicates,
                "recovery": {"spiked": measured, "unspiked": unspiked, "added": added},
                "sample_signals": samples_text or None,
            },
            settings={"weighting": weights, "blank_sd": blank_sd or None},
            result={
                **dict(zip(summary["quantity"], summary["value"], strict=True)),
                "sample_x0": None if sample is None else sample.x0,
                "sample_u_x0": None if sample is None else sample.u_x0,
            },
        )
    )


LABEL_COLOURS = {"ok": "green", "straggler": "orange", "outlier": "red"}


def outlier_badge(label: str) -> str:
    return f":{LABEL_COLOURS[label]}[**{label}**]"


with tab_outliers:
    inputs, results = columns()
    with inputs:
        st.subheader("Inputs")
        st.button("Load example data", on_click=load_outliers, key="ol_load")
        st.markdown("**Replicate results** for the Grubbs tests")
        ol_text = st.text_area("Results", key="ol_values", height=90)
        st.markdown("**Groups of replicates** for Cochran's test (one row per lab or day)")
        groups_table = st.data_editor(
            st.session_state.ol_groups,
            key=f"ol_groups_editor_{st.session_state.ol_version}",
            num_rows="dynamic",
            width="stretch",
        )
        remember("ol_groups", groups_table)
        st.caption("The first column names the group; the other columns hold its replicates.")

    with results:
        st.subheader("Grubbs tests (ISO 5725-2)")
        with friendly_errors():
            ol_values = parse_numbers(ol_text, "Results")
            g1 = grubbs(ol_values)
            g2 = grubbs_two(ol_values)
        m1, m2, m3 = st.columns(3)
        m1.metric("Grubbs, one value: G", f"{g1.statistic:.3f}")
        m2.metric("Critical 5 % / 1 %", f"{g1.critical_95:.3f} / {g1.critical_99:.3f}")
        m3.markdown(f"Suspect **{g1.suspect[0]:g}** ({g1.side})  \n{outlier_badge(g1.label)}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Grubbs, two values: G", f"{g2.statistic:.4f}")
        m2.metric("Critical 5 % / 1 %", f"{g2.critical_95:.4f} / {g2.critical_99:.4f}")
        pair = ", ".join(f"{v:g}" for v in g2.suspect)
        m3.markdown(f"Suspects **{pair}** ({g2.side})  \n{outlier_badge(g2.label)}")
        flagged = set(g1.index) if g1.label != "ok" else set()
        fig_o = go.Figure(
            go.Scatter(
                x=list(range(1, len(ol_values) + 1)), y=ol_values, mode="markers",
                marker={"size": 11, "color": ["#c0392b" if i in flagged else "#2c6e8f"
                                              for i in range(len(ol_values))]},
            )
        )  # fmt: skip
        fig_o.update_layout(height=260, margin={"t": 20}, xaxis_title="result no.",
                            yaxis_title="value")  # fmt: skip
        st.plotly_chart(fig_o, width="stretch")
        st.caption(
            "Grubbs: G above the critical value is significant. Two values: G *below* the "
            "critical value is significant. Two-value critical values are simulated."
        )

        st.subheader("Cochran's test")
        with friendly_errors():
            groups = groups_table.dropna(how="all")
            if groups.shape[1] < 3:
                raise ValueError("Give a group name and at least two replicate columns")
            names = groups.iloc[:, 0].astype(str).tolist()
            reps = groups.iloc[:, 1:].apply(pd.to_numeric, errors="raise")
            if reps.isna().any().any():
                raise ValueError("Every group needs a result in every replicate column")
            ch = cochran(reps.to_numpy().tolist())
        m1, m2, m3 = st.columns(3)
        m1.metric("Cochran C", f"{ch.statistic:.3f}")
        m2.metric("Critical 5 % / 1 %", f"{ch.critical_95:.3f} / {ch.critical_99:.3f}")
        m3.markdown(f"Largest variance: **{names[ch.index[0]]}**  \n{outlier_badge(ch.label)}")
        variances = reps.var(axis=1, ddof=1)
        fig_c = go.Figure(
            go.Bar(x=names, y=variances, marker_color=[
                "#c0392b" if i == ch.index[0] and ch.label != "ok" else "#2c6e8f"
                for i in range(len(names))])
        )  # fmt: skip
        fig_c.update_layout(height=240, margin={"t": 20}, yaxis_title="variance")
        st.plotly_chart(fig_c, width="stretch")
        what_this_means(explain.outliers(g1, g2, ch, names[ch.index[0]]))

    export_header()
    report_button(
        lambda: RunRecord(
            "labqc.outliers",
            title="Outlier tests",
            method=(
                "Grubbs tests for one and two outliers and Cochran's test for the largest "
                "variance (ISO 5725-2): significant at 5 % = straggler, at 1 % = outlier."
            ),
            inputs={"values": ol_values, "groups": groups},
            result={
                "grubbs": {"G": g1.statistic, "critical_95": g1.critical_95,
                           "critical_99": g1.critical_99, "suspect": g1.suspect[0],
                           "label": g1.label},
                "grubbs_two": {"G": g2.statistic, "critical_95": g2.critical_95,
                               "critical_99": g2.critical_99, "suspects": list(g2.suspect),
                               "label": g2.label},
                "cochran": {"C": ch.statistic, "critical_95": ch.critical_95,
                            "critical_99": ch.critical_99, "group": names[ch.index[0]],
                            "label": ch.label},
            },
        ),
        key="ol_report",
    )  # fmt: skip


with tab_compare:
    inputs, results = columns()
    with inputs:
        st.subheader("Inputs")
        st.button("Load example data", on_click=load_comparison, key="cmp_load")
        cmp_table = st.data_editor(
            st.session_state.cmp_table,
            key=f"cmp_editor_{st.session_state.cmp_version}",
            num_rows="dynamic",
            width="stretch",
            height=320,
        )
        remember("cmp_table", cmp_table)
        numeric = [c for c in cmp_table.columns if c != "sample"]
        c1, c2 = st.columns(2)
        x_col = c1.selectbox("Reference or old method (x)", numeric, key="cmp_x")
        y_col = c2.selectbox("New method (y)", numeric, key="cmp_y", index=min(1, len(numeric) - 1))
        c1, c2 = st.columns(2)
        line_method = c1.radio("Regression", ["Passing-Bablok", "Deming"], key="cmp_method")
        ratio = c2.number_input(
            "Deming error ratio, var(y) / var(x)", min_value=0.01, step=0.1, key="cmp_ratio",
            disabled=line_method != "Deming",
        )  # fmt: skip

    with results:
        st.subheader("Method comparison")
        with friendly_errors():
            if x_col == y_col:
                raise ValueError("Choose two different columns for x and y")
            pairs = cmp_table[[x_col, y_col]].apply(pd.to_numeric, errors="raise").dropna()
            xs, ys = pairs[x_col].to_numpy(), pairs[y_col].to_numpy()
            ba = bland_altman(xs, ys)
            line = (
                passing_bablok(xs, ys)
                if line_method == "Passing-Bablok"
                else deming(xs, ys, error_ratio=ratio)
            )
        m1, m2, m3 = st.columns(3)
        m1.metric("Bias (y − x)", f"{ba.bias:.3g}",
                  help=f"95 % CI {ba.bias_ci95[0]:.3g} to {ba.bias_ci95[1]:.3g}")  # fmt: skip
        m2.metric("Limits of agreement", f"{ba.loa[0]:.3g} to {ba.loa[1]:.3g}")
        m3.metric("Samples", ba.n)
        fig_ba = go.Figure(go.Scatter(x=ba.mean, y=ba.diff, mode="markers",
                                      marker={"color": "#2c6e8f"}, name="samples"))  # fmt: skip
        for yv, dash, name in ((ba.bias, "solid", "bias"), (ba.loa[0], "dash", "−1.96 s"),
                               (ba.loa[1], "dash", "+1.96 s")):  # fmt: skip
            fig_ba.add_hline(y=yv, line_dash=dash, line_color="black", line_width=1,
                             annotation_text=name, annotation_position="right")  # fmt: skip
        fig_ba.add_hline(y=0, line_color="grey", line_width=1)
        fig_ba.update_layout(height=300, margin={"t": 30, "r": 60}, title="Bland-Altman plot",
                             xaxis_title="mean of x and y", yaxis_title="y − x")  # fmt: skip
        st.plotly_chart(fig_ba, width="stretch")

        m1, m2, m3 = st.columns(3)
        m1.metric("Comparison slope", f"{line.slope:.4f}",
                  help=f"95 % CI {line.slope_ci95[0]:.4f} to {line.slope_ci95[1]:.4f}")  # fmt: skip
        lo_a, hi_a = line.intercept_ci95
        m2.metric(
            "Comparison intercept",
            f"{line.intercept:.3g}",
            help=f"95 % CI {lo_a:.3g} to {hi_a:.3g}",
        )
        m3.metric("Agreement with y = x", "yes" if line.agrees else "no")
        ends = [float(min(xs.min(), ys.min())), float(max(xs.max(), ys.max()))]
        fig_r = go.Figure()
        fig_r.add_trace(go.Scatter(x=xs, y=ys, mode="markers", name="samples",
                                   marker={"color": "#2c6e8f"}))  # fmt: skip
        fig_r.add_trace(go.Scatter(x=ends, y=line.predict(ends), mode="lines", name=line_method,
                                   line={"color": "#c0392b"}))  # fmt: skip
        fig_r.add_trace(go.Scatter(x=ends, y=ends, mode="lines", name="y = x",
                                   line={"color": "grey", "dash": "dash"}))  # fmt: skip
        fig_r.update_layout(height=340, margin={"t": 30}, xaxis_title=x_col, yaxis_title=y_col,
                            legend={"orientation": "h", "y": 1.1})  # fmt: skip
        st.plotly_chart(fig_r, width="stretch")
        if line.linear is not None:
            st.caption(
                "Linearity (cusum test): "
                f"{'no significant deviation' if line.linear else 'NOT linear'}"
                f" (max cusum {line.cusum:.2f}, critical {line.cusum_critical:.2f})."
            )
        what_this_means(explain.comparison(ba, line, line_method))

    export_header()
    report_button(
        lambda: RunRecord(
            "labqc.comparison",
            title="Method comparison",
            method=(
                "Bland-Altman bias and 95 % limits of agreement; "
                + (
                    "Passing-Bablok regression with rank-based 95 % intervals and cusum "
                    "linearity test."
                    if line_method == "Passing-Bablok"
                    else f"Deming regression (error ratio {ratio:g}) with jackknife 95 % "
                    "intervals."
                )
            ),
            inputs={"pairs": pairs},
            settings={"x": x_col, "y": y_col, "regression": line_method},
            result={
                "bias": ba.bias, "loa": list(ba.loa), "slope": line.slope,
                "slope_ci95": list(line.slope_ci95), "intercept": line.intercept,
                "intercept_ci95": list(line.intercept_ci95), "agrees": line.agrees,
                "linear": line.linear,
            },
        ),
        key="cmp_report",
    )  # fmt: skip

footer()
