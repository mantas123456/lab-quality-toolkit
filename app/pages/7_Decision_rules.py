"""Decision rules page: pass / fail with measurement uncertainty (labqc.conformity)."""

import explain
import plotly.graph_objects as go
import streamlit as st
from common import (
    columns,
    deep_link,
    examples,
    export_header,
    footer,
    friendly_errors,
    page,
    report_button,
    what_this_means,
)

from labqc.conformity import RULES, decide
from labqc.report import RunRecord

PAGE = "pages/7_Decision_rules.py"
OUTCOME_COLOURS = {
    "pass": "#2e7d32",
    "conditional pass": "#7cb342",
    "no clear decision": "#e0a100",
    "conditional fail": "#ef6c00",
    "fail": "#c0392b",
}
RULE_HELP = {
    "simple": "Pass when the value is inside the limits; U is reported but not used.",
    "guarded": "Pass only inside the limits by more than w; fail only outside by more than w; "
    "otherwise no clear decision.",
    "non-binary": "Pass, conditional pass, conditional fail or fail, with a guard band w.",
}

page(
    "Decision rules",
    "State conformity with a specification when the result has an uncertainty: simple "
    "acceptance, or a guard band (ILAC G8:09/2019, JCGM 106:2012).",
)


def load(rule: str) -> None:
    ex = examples()["decision"]
    st.session_state.dec_value = ex["value"]
    st.session_state.dec_U = ex["U"]
    st.session_state.dec_k = ex["k"]
    st.session_state.dec_unit = ex["unit"]
    st.session_state.dec_has_lower = False
    st.session_state.dec_lower = 0.0
    st.session_state.dec_has_upper = True
    st.session_state.dec_upper = ex["upper"]
    st.session_state.dec_rule = rule
    st.session_state.dec_r = 1.0


def load_example() -> None:
    load("simple")


deep_link(PAGE, {"decision": load_example, "decision-guarded": lambda: load("non-binary")})
if "dec_value" not in st.session_state:
    load_example()

inputs, results = columns()

with inputs:
    st.subheader("Inputs")
    st.button("Load example data", on_click=load_example)
    st.caption(f"Example: {examples()['decision']['what']}.")
    c1, c2 = st.columns(2)
    value = c1.number_input("Result y", key="dec_value", format="%.4g")
    unit = c2.text_input("Unit", key="dec_unit")
    c1, c2 = st.columns(2)
    U = c1.number_input("Expanded uncertainty U", min_value=0.0, key="dec_U", format="%.4g")
    k = c2.number_input("Coverage factor k", min_value=0.1, key="dec_k", step=0.1)
    st.markdown("**Specification**")
    c1, c2 = st.columns(2)
    has_lower = c1.checkbox("Lower limit", key="dec_has_lower")
    lower = c1.number_input(
        "Lower limit", key="dec_lower", format="%.4g", disabled=not has_lower,
        label_visibility="collapsed",
    )  # fmt: skip
    has_upper = c2.checkbox("Upper limit", key="dec_has_upper")
    upper = c2.number_input(
        "Upper limit", key="dec_upper", format="%.4g", disabled=not has_upper,
        label_visibility="collapsed",
    )  # fmt: skip
    rule = st.radio(
        "Decision rule", RULES, key="dec_rule", horizontal=True, captions=None,
        help="\n\n".join(f"**{r}**: {t}" for r, t in RULE_HELP.items()),
    )  # fmt: skip
    st.caption(RULE_HELP[rule])
    r = st.number_input(
        "Guard band w as a multiple of U (w = r U)", min_value=0.0, step=0.25, key="dec_r",
        disabled=rule == "simple",
    )  # fmt: skip

with results:
    st.subheader("Decision")
    with friendly_errors():
        d = decide(
            value,
            U,
            lower=lower if has_lower else None,
            upper=upper if has_upper else None,
            rule=rule,
            guard_band=None if rule == "simple" else r * U,
            k=k,
            unit=unit,
        )
    colour = OUTCOME_COLOURS[d.outcome]
    st.markdown(
        f"<div style='font-size:2rem;font-weight:600;color:{colour}'>{d.outcome.upper()}</div>",
        unsafe_allow_html=True,
    )
    m1, m2, m3 = st.columns(3)
    m1.metric("Outcome", d.outcome)
    m2.metric("Probability of conformance", f"{d.probability:.1%}", help="u = U / k, normal")
    m3.metric("Guard band w", f"{d.guard_band:.4g}")

    # picture: the result with its interval against the limits, guard bands shaded
    edges = [x for x in (d.lower, d.upper) if x is not None]
    span = max([abs(value - e) for e in edges] + [U, 1e-9])
    lo_x = min([value - U, *edges, *(x for x in (d.rejection_lower,) if x is not None)])
    hi_x = max([value + U, *edges, *(x for x in (d.rejection_upper,) if x is not None)])
    pad = 0.35 * max(hi_x - lo_x, span)
    x0, x1 = lo_x - pad, hi_x + pad
    fig = go.Figure()

    def band(a, b, fill, name):
        if a is not None and b is not None and b > a:
            fig.add_vrect(x0=a, x1=b, fillcolor=fill, opacity=0.18, line_width=0,
                          annotation_text=name, annotation_position="top")  # fmt: skip

    band(d.acceptance_lower if d.lower is not None else x0,
         d.acceptance_upper if d.upper is not None else x1, "#2e7d32", "accept")  # fmt: skip
    if d.guard_band:
        if d.lower is not None:
            band(d.rejection_lower, d.acceptance_lower, "#e0a100", "guard band")
        if d.upper is not None:
            band(d.acceptance_upper, d.rejection_upper, "#e0a100", "guard band")
    if d.lower is not None:
        band(x0, d.rejection_lower, "#c0392b", "reject")
    if d.upper is not None:
        band(d.rejection_upper, x1, "#c0392b", "reject")
    for edge, name in ((d.lower, "lower limit"), (d.upper, "upper limit")):
        if edge is not None:
            fig.add_vline(x=edge, line_color="black", line_width=2,
                          annotation_text=name, annotation_position="bottom")  # fmt: skip
    fig.add_trace(
        go.Scatter(
            x=[value], y=[0], mode="markers", marker={"size": 14, "color": colour},
            error_x={"type": "constant", "value": U, "thickness": 2, "width": 10,
                     "color": colour},
            name="y ± U", hovertemplate=f"y = {value:.4g} ± {U:.3g}<extra></extra>",
        )
    )  # fmt: skip
    fig.update_layout(
        height=240, margin={"t": 40, "b": 40}, showlegend=False,
        xaxis={"range": [x0, x1], "title": unit or "value"},
        yaxis={"visible": False, "range": [-1, 1]},
    )  # fmt: skip
    st.plotly_chart(fig, width="stretch")
    what_this_means(explain.decision(d.outcome, d.rule, d.probability, d.guard_band))
    st.markdown("**Suggested report wording**")
    st.code(d.wording, language=None, wrap_lines=True)

export_header()
report_button(
    lambda: RunRecord(
        "labqc.conformity.decide",
        title="Decision rule",
        method=(
            f"Conformity statement by {explain.RULE_NAMES[d.rule]} (ILAC G8:09/2019); guard "
            "band w = r U; probability of conformance from a normal distribution with "
            "u = U / k (JCGM 106:2012)."
        ),
        inputs={"value": value, "U": U, "k": k, "unit": unit, "lower": d.lower, "upper": d.upper},
        settings={"rule": d.rule, "guard_band": d.guard_band},
        result={
            "outcome": d.outcome,
            "acceptance_lower": d.acceptance_lower,
            "acceptance_upper": d.acceptance_upper,
            "probability_of_conformance": d.probability,
            "wording": d.wording,
        },
    )
)
footer()
