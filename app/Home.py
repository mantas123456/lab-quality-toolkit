"""labqc web app: home page. Run with `streamlit run app/Home.py`."""

import streamlit as st
from common import footer, labqc, page

page(
    "labqc: laboratory quality calculations",
    "The calculations an ISO/IEC 17025 laboratory does every week, in the browser. "
    "Every number comes from the tested labqc Python library.",
)

st.markdown(
    "Each page opens with example data already loaded, so you can see a real result at "
    "once. Edit the inputs or upload your own CSV, then download the results."
)

pages = [
    (
        "pages/1_Uncertainty_budget.py",
        "Uncertainty budget",
        "GUM budget: u_c, k from v_eff, U, and which component dominates.",
    ),
    (
        "pages/2_Method_validation.py",
        "Method validation",
        "Calibration line, residuals, LOD/LOQ, precision and recovery.",
    ),
    (
        "pages/3_Proficiency_testing.py",
        "Proficiency testing",
        "z, zeta and En scores; robust mean and SD for a round (Algorithm A).",
    ),
    (
        "pages/4_QC_charts.py",
        "QC charts",
        "Levey-Jennings chart with Westgard rules from a CSV of control results.",
    ),
    (
        "pages/5_Emissions.py",
        "Emissions",
        "ppm to mg/m3, dry, standard conditions, reference O2, and % of the limit.",
    ),
    (
        "pages/6_Reports.py",
        "Reports",
        "PDF, Excel and JSON records of your results; reload a saved budget.",
    ),
]
left, right = st.columns(2, gap="large")
for i, (path, label, text) in enumerate(pages):
    with left if i % 2 == 0 else right:
        with st.container(border=True):
            st.page_link(path, label=f"**{label}**")
            st.caption(text)

st.markdown(
    "Library: `pip install labqc` · "
    "[Documentation](https://mantas123456.github.io/lab-quality-toolkit/) · "
    "[Source on GitHub](https://github.com/mantas123456/lab-quality-toolkit)"
)
st.info(
    f"This app runs labqc {labqc.__version__}, checked against published and hand-calculated "
    "reference cases ([validation report](https://mantas123456.github.io/lab-quality-toolkit/"
    "validation/)). Before you report results, validate it for your own use."
)
footer()
