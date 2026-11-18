"""Reports page: placeholder until version 0.6."""

import streamlit as st
from common import footer, page

page("Reports", "PDF and Excel reports of your results.")

st.info(
    "**Coming in 0.6.** Every result will be exportable as a one-page PDF and an Excel file "
    "with its inputs, method, result, labqc version and date, and saved budgets can be "
    "reloaded. Until then, each page has CSV downloads at the bottom."
)
footer()
