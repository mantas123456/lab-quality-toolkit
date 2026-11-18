"""Reports page: records made in this session -> PDF, Excel, JSON; reload a saved budget."""

import io
from dataclasses import replace

import pandas as pd
import streamlit as st
from common import columns, footer, page

from labqc.report import RunRecord, budget_from_record, to_excel, to_pdf

page(
    "Reports",
    "Results you added with 'Add to report' on the other pages, as a PDF per result, one "
    "Excel workbook, or JSON records you can reload later.",
)

records: list[RunRecord] = st.session_state.setdefault("records", [])


def load_json() -> None:
    file = st.session_state.get("report_upload")
    if file is None:
        return
    try:
        record = RunRecord.from_json(file.getvalue())
    except ValueError as err:
        st.session_state.report_upload_error = str(err)
        return
    st.session_state.pop("report_upload_error", None)
    st.session_state.report_loaded = record
    st.session_state.records.append(record)


def open_in_uncertainty(record: RunRecord) -> None:
    table, info = budget_from_record(record)
    st.session_state.unc_table = table
    st.session_state.unc_y = float(info["value"] or 0.0)
    st.session_state.unc_unit = info["unit"] or ""
    if info["coverage"] in (0.90, 0.95, 0.99):
        st.session_state.unc_coverage = info["coverage"]
    st.session_state.unc_k = float(info["fixed_k"] or 0.0)
    st.session_state.unc_version = st.session_state.get("unc_version", 0) + 1


def pdf_bytes(record: RunRecord) -> bytes:
    buffer = io.BytesIO()
    to_pdf(record, buffer)
    return buffer.getvalue()


def excel_bytes(items: list[RunRecord]) -> bytes:
    buffer = io.BytesIO()
    to_excel(items, buffer)
    return buffer.getvalue()


def slug(record: RunRecord) -> str:
    stamp = record.timestamp[:19].replace(":", "").replace("-", "")
    return f"{record.label().lower().replace(' ', '_')}_{stamp}"


left, right = columns()

with left:
    st.subheader("Records in this session")
    analyst = st.text_input(
        "Analyst (optional, printed on the reports)", key="analyst", max_chars=80
    )
    if not records:
        st.info("No records yet. Use **Add to report** at the bottom of any page.")
    else:
        st.dataframe(
            pd.DataFrame(
                {
                    "#": range(1, len(records) + 1),
                    "result": [r.label() for r in records],
                    "function": [r.function for r in records],
                    "time (UTC)": [r.timestamp[11:19] for r in records],
                }
            ),
            hide_index=True,
            width="stretch",
        )
        if st.button("Clear all records"):
            records.clear()
            st.rerun()

    st.subheader("Reload a saved record")
    st.file_uploader(
        "Upload a .json record saved from this page",
        type="json",
        key="report_upload",
        on_change=load_json,
    )
    if "report_upload_error" in st.session_state:
        st.error(st.session_state.report_upload_error)
    loaded = st.session_state.get("report_loaded")
    if loaded is not None:
        st.success(
            f"Loaded **{loaded.label()}** from {loaded.timestamp} (labqc {loaded.labqc_version})."
        )
        if loaded.function == "labqc.uncertainty.combine":
            if st.button("Open this budget in Uncertainty budget", type="primary"):
                open_in_uncertainty(loaded)
                st.switch_page("pages/1_Uncertainty_budget.py")

with right:
    st.subheader("Download")
    if records:
        signed = [replace(r, analyst=analyst or r.analyst) for r in records]
        st.download_button(
            f"Excel workbook, all {len(signed)} record(s)",
            excel_bytes(signed),
            "labqc_records.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
        index = st.selectbox(
            "One record as PDF or JSON",
            range(len(signed)),
            index=len(signed) - 1,
            format_func=lambda i: f"{i + 1}. {signed[i].label()} ({signed[i].timestamp[11:19]})",
        )
        chosen = signed[index]
        c1, c2 = st.columns(2)
        c1.download_button(
            "PDF report", pdf_bytes(chosen), f"{slug(chosen)}.pdf", "application/pdf"
        )
        c2.download_button(
            "JSON record",
            chosen.to_json().encode("utf-8"),
            f"{slug(chosen)}.json",
            "application/json",
        )
        st.caption(
            "The JSON record keeps every input, setting and result with the labqc version and "
            "time. An uncertainty budget saved as JSON can be reloaded on the left."
        )
    else:
        st.caption("Downloads appear here once there is at least one record.")

footer()
