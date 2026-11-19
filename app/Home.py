"""labqc web app: home page. Run with `streamlit run app/Home.py`."""

import streamlit as st
from common import EXAMPLES, example_url, footer, labqc, page

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
        "GUM budget with correlations and a Monte Carlo check; top-down from QC and PT data.",
    ),
    (
        "pages/2_Method_validation.py",
        "Method validation",
        "Calibration line, residuals, LOD/LOQ, precision and recovery.",
    ),
    (
        "pages/3_Proficiency_testing.py",
        "Proficiency testing",
        "z, zeta and En; robust mean and SD of a round; z-scores across rounds.",
    ),
    (
        "pages/4_QC_charts.py",
        "QC charts",
        "Westgard rules for one or several levels, CUSUM and EWMA charts.",
    ),
    (
        "pages/5_QC_overview.py",
        "QC overview",
        "Every method and control level in one grid: the Westgard status of the latest run.",
    ),
    (
        "pages/6_Emissions.py",
        "Emissions",
        "ppm to mg/m3, dry, standard conditions, reference O2, and % of the limit.",
    ),
    (
        "pages/7_Decision_rules.py",
        "Decision rules",
        "Pass or fail with uncertainty: simple acceptance or a guard band (ILAC G8).",
    ),
    (
        "pages/8_Reports.py",
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

st.caption(
    "This app also runs entirely in your browser, with no server: "
    "[labqc in your browser](https://mantas123456.github.io/lab-quality-toolkit/app/). "
    "Use *Save project* in the sidebar to keep your inputs in one file."
)

st.subheader("Open an example directly")
st.markdown(
    "Add `?example=<name>` to a page's address to open it with that example loaded, "
    "for example from a handbook or a training note."
)
st.markdown(
    "\n".join(
        f"- [`{name}`]({example_url(name)}) · {label}: {text}"
        for name, (_, label, text) in EXAMPLES.items()
    )
)

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
