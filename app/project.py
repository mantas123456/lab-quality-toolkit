"""Project files for the web app: the whole session in one .labqc.json file.

A project keeps the inputs of every page (budgets, top-down data, calibration, PT round and
history, QC series, overview, emissions, decision checks) and the report records, so work can
be closed and reopened later or passed to a colleague. Only inputs are saved: every result is
calculated again by labqc when the project is opened.

The file is JSON:

    {"format": "labqc-project", "version": 1, "labqc_version": "1.3.0",
     "saved": "2026-11-19T08:00:00+00:00",
     "pages": {"uncertainty": {"unc_y": 6.97, "unc_table": {"columns": [...], "rows": [...]}},
               ...},
     "records": [<RunRecord JSON>, ...]}

`loads` checks the structure before anything is changed (the schema check): an unknown
format, a newer version, an unknown page or input, or a malformed table is refused with a
plain message, and the session stays as it was.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, MutableMapping
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from labqc.report import RunRecord

FORMAT = "labqc-project"
VERSION = 1
SUFFIX = ".labqc.json"

# The session-state keys of each page's inputs.
PAGES: dict[str, tuple[str, ...]] = {
    "uncertainty": ("unc_table", "unc_y", "unc_unit", "unc_coverage", "unc_k", "unc_corr"),
    "topdown": (
        "td_qc", "td_dup", "td_pt", "td_crm_results", "td_crm_certified", "td_crm_u",
        "td_source", "td_relative", "td_k",
    ),
    "validation": (
        "val_table", "val_weights", "val_blank_sd", "val_replicates", "val_measured",
        "val_unspiked", "val_added",
    ),
    "proficiency": (
        "pt_x", "pt_assigned", "pt_sigma_pt", "pt_u_x", "pt_u_assigned", "pt_U_x",
        "pt_U_assigned", "pt_table", "pt_hist_table",
    ),
    "qc": (
        "qc_table", "qc_mode", "qc_baseline", "qc_method", "qc_centre", "qc_sd", "qc_across",
        "qc_cusum_k", "qc_cusum_h", "qc_ewma_lam", "qc_ewma_L",
    ),
    "qc_overview": ("qcov_table", "qcov_baseline", "qcov_method"),
    "emissions": (
        "em_table", "em_o2_measured", "em_o2_ref", "em_water_vol_fraction", "em_t_c", "em_p_kpa",
    ),
    "decision": (
        "dec_value", "dec_U", "dec_k", "dec_unit", "dec_has_lower", "dec_lower",
        "dec_has_upper", "dec_upper", "dec_rule", "dec_r",
    ),
}  # fmt: skip

# Counters in the pages' data-editor keys; bumping them makes the editors show loaded tables.
EDITOR_VERSIONS = ("unc_version", "td_version", "val_version", "pt_version", "pt_hist_version",
                   "em_version")  # fmt: skip

EDITED = "__edited"  # suffix of the key that holds a data editor's current (edited) table


def _cell(value: Any) -> Any:
    """A table cell as plain JSON: NaN and None become null, numpy numbers become Python."""
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _table(df: pd.DataFrame) -> dict:
    return {
        "columns": [str(c) for c in df.columns],
        "rows": [[_cell(v) for v in row] for row in df.itertuples(index=False)],
    }


def _scalar(value: Any) -> Any:
    value = _cell(value)
    if not isinstance(value, (bool, int, float, str)) and value is not None:
        raise TypeError(f"cannot save a {type(value).__name__}")
    return value


def collect(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The inputs of every page found in `state`; edited tables win over the loaded ones."""
    pages: dict[str, dict[str, Any]] = {}
    for name, keys in PAGES.items():
        values = {}
        for key in keys:
            value = state.get(key + EDITED, state.get(key))
            if value is None and key not in state:
                continue
            values[key] = _table(value) if isinstance(value, pd.DataFrame) else _scalar(value)
        if values:
            pages[name] = values
    return pages


def dumps(state: Mapping[str, Any], labqc_version: str) -> str:
    records = [json.loads(r.to_json()) for r in state.get("records", [])]
    project = {
        "format": FORMAT,
        "version": VERSION,
        "labqc_version": labqc_version,
        "saved": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pages": collect(state),
        "records": records,
    }
    return json.dumps(project, indent=1, ensure_ascii=False, allow_nan=False)


def _check_table(where: str, value: Any) -> pd.DataFrame:
    if set(value) != {"columns", "rows"}:
        raise ValueError(f"{where}: a table needs exactly 'columns' and 'rows'")
    columns, rows = value["columns"], value["rows"]
    if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
        raise ValueError(f"{where}: columns must be a list of names")
    if not isinstance(rows, list):
        raise ValueError(f"{where}: rows must be a list")
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, list) or len(row) != len(columns):
            raise ValueError(f"{where}: row {i} must have {len(columns)} cells")
        if not all(isinstance(c, (bool, int, float, str)) or c is None for c in row):
            raise ValueError(f"{where}: row {i} has a cell that is not a number or text")
    return pd.DataFrame(rows, columns=columns)


def loads(text: str | bytes) -> tuple[dict[str, Any], list[RunRecord]]:
    """Check a project file and return (session-state values, records). Raises ValueError."""
    try:
        project = json.loads(text)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("This is not a labqc project file (it is not valid JSON)") from None
    if not isinstance(project, dict) or project.get("format") != FORMAT:
        raise ValueError("This is not a labqc project file (format is not 'labqc-project')")
    version = project.get("version")
    if not isinstance(version, int) or version < 1:
        raise ValueError("The project file has no valid version number")
    if version > VERSION:
        raise ValueError(
            f"This project was saved by a newer labqc (file version {version}); "
            f"this app reads version {VERSION}. Update the app to open it."
        )
    unknown = set(project) - {"format", "version", "labqc_version", "saved", "pages", "records"}
    if unknown:
        raise ValueError(f"Unknown entries in the project file: {', '.join(sorted(unknown))}")
    pages = project.get("pages", {})
    if not isinstance(pages, dict):
        raise ValueError("'pages' must be an object")
    values: dict[str, Any] = {}
    for name, inputs in pages.items():
        if name not in PAGES:
            raise ValueError(f"Unknown page in the project file: {name!r}")
        if not isinstance(inputs, dict):
            raise ValueError(f"{name}: the inputs must be an object")
        for key, value in inputs.items():
            if key not in PAGES[name]:
                raise ValueError(f"{name}: unknown input {key!r}")
            if isinstance(value, dict):
                values[key] = _check_table(f"{name}.{key}", value)
            elif isinstance(value, (bool, int, float, str)) or value is None:
                values[key] = value
            else:
                raise ValueError(f"{name}.{key}: must be a number, text, true/false or a table")
    raw_records = project.get("records", [])
    if not isinstance(raw_records, list):
        raise ValueError("'records' must be a list")
    records = []
    for i, raw in enumerate(raw_records, start=1):
        try:
            records.append(RunRecord.from_json(json.dumps(raw)))
        except (ValueError, TypeError) as err:
            raise ValueError(f"Record {i}: {err}") from None
    return values, records


def apply(state: MutableMapping[str, Any], values: Mapping[str, Any], records: list) -> None:
    """Put loaded values into the session, so every page opens with them."""
    for key, value in values.items():
        state[key] = value
        if key + EDITED in state:
            del state[key + EDITED]
    for key in EDITOR_VERSIONS:
        state[key] = state.get(key, 0) + 1
    state["records"] = list(records)
