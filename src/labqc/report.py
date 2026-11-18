"""Records and reports: keep what was calculated, with what, by which version, and when.

A RunRecord holds one calculation: the labqc function, its inputs and settings,
the result, a short description of the method, the labqc version, a UTC
timestamp and optionally the analyst. Records round-trip through JSON, so a
saved budget can be reloaded later, and can be written to Excel (one sheet per
record) or to a one-page PDF.

Excel and PDF output need the [reports] extra: pip install "labqc[reports]".
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

import numpy as np
import pandas as pd

from . import __version__
from .uncertainty import TABLE_COLUMNS, Component, Result

PathOrFile = str | Path | IO[bytes]

BUDGET_FUNCTION = "labqc.uncertainty.combine"
BUDGET_METHOD = (
    "GUM (JCGM 100:2008): u_c = sqrt(sum((c_i * u_i)^2)) for uncorrelated inputs; "
    "effective degrees of freedom by Welch-Satterthwaite; coverage factor k from Student's t "
    "unless fixed; U = k * u_c."
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def plain(value: Any) -> Any:
    """Turn numpy, pandas and float edge cases into plain JSON values.

    Infinity becomes the string "inf" (JSON has no infinity), NaN becomes None,
    DataFrames become lists of row dicts and tuples become lists.
    """
    if isinstance(value, pd.DataFrame):
        return [plain(row) for row in value.to_dict(orient="records")]
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray, pd.Series)):
        return [plain(v) for v in list(value)]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        value = float(value)
        if math.isnan(value):
            return None
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return value
    if value is None or isinstance(value, (str, int)):
        return value
    return str(value)


@dataclass
class RunRecord:
    """One calculation, kept as a record.

    function: the labqc function that made the result, e.g. "labqc.uncertainty.combine".
    inputs, settings, result: plain dictionaries (numbers, strings, lists, and lists of
    row dicts for tables). method: one or two sentences naming the formula or standard.
    """

    function: str
    inputs: dict[str, Any]
    settings: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    method: str = ""
    title: str = ""
    analyst: str | None = None
    labqc_version: str = __version__
    timestamp: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.inputs = plain(self.inputs)
        self.settings = plain(self.settings)
        self.result = plain(self.result)

    def to_json(self) -> str:
        """The record as indented JSON (UTF-8 text, keys in a fixed order)."""
        return json.dumps(asdict(self), indent=2, ensure_ascii=False, allow_nan=False) + "\n"

    @classmethod
    def from_json(cls, text: str | bytes) -> RunRecord:
        """Read a record saved with `to_json`. Raises ValueError for anything else."""
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise ValueError(f"Not a valid labqc record: {err}") from None
        if not isinstance(data, dict):
            raise ValueError("Not a valid labqc record: expected a JSON object")
        known = {f.name for f in fields(cls)}
        missing = {"function", "inputs"} - set(data)
        if missing:
            raise ValueError(f"Not a valid labqc record: missing {', '.join(sorted(missing))}")
        unknown = set(data) - known
        if unknown:
            raise ValueError(
                f"Not a valid labqc record: unknown field(s) {', '.join(sorted(unknown))}"
            )
        return cls(**data)

    def label(self) -> str:
        return self.title or self.function.rsplit(".", 1)[-1]


# --- uncertainty budgets -----------------------------------------------------------------


def record_budget(
    components: Sequence[Component],
    result: Result,
    coverage: float | None = None,
    fixed_k: float | None = None,
    unit: str = "",
    title: str = "Uncertainty budget",
    analyst: str | None = None,
) -> RunRecord:
    """Record a budget made with `combine` (or `propagate`) so it can be reported and reloaded."""
    return RunRecord(
        function=BUDGET_FUNCTION,
        title=title,
        analyst=analyst,
        method=BUDGET_METHOD,
        inputs={
            "value": result.value,
            "unit": unit,
            "components": [
                {
                    "name": c.name,
                    "value": c.value,
                    "distribution": c.distribution,
                    "k": c.k,
                    "sensitivity": c.sensitivity,
                    "dof": c.dof,
                    "unit": c.unit,
                }
                for c in components
            ],
        },
        settings={
            "coverage": result.coverage if coverage is None else coverage,
            "fixed_k": fixed_k,
        },
        result={
            "combined_u_c": result.combined,
            "effective_dof": result.effective_dof,
            "k": result.k,
            "expanded_U": result.expanded,
            "relative_U": result.relative_expanded if result.value else None,
            "budget": result.table,
        },
    )


def budget_from_record(record: RunRecord) -> tuple[pd.DataFrame, dict[str, Any]]:
    """The components table and settings of a recorded budget, ready for `combine` again.

    Returns (table with the columns of `components_from_table`, dict with value, unit,
    coverage and fixed_k). Raises ValueError if the record is not an uncertainty budget.
    """
    if record.function != BUDGET_FUNCTION or "components" not in record.inputs:
        raise ValueError(
            f"This record is not an uncertainty budget (it was made by {record.function})"
        )
    table = pd.DataFrame(record.inputs["components"]).reindex(columns=list(TABLE_COLUMNS))
    table["dof"] = [
        None if d in ("inf", None) else float(d) for d in table["dof"]
    ]  # blank = infinite
    info = {
        "value": record.inputs.get("value"),
        "unit": record.inputs.get("unit", ""),
        "coverage": record.settings.get("coverage", 0.95),
        "fixed_k": record.settings.get("fixed_k"),
    }
    return table, info


# --- shared layout for Excel and PDF -----------------------------------------------------


def _sections(record: RunRecord) -> list[tuple[str, list[tuple[str, Any]], list[tuple[str, list]]]]:
    """(heading, key/value rows, named tables) for Inputs, Settings and Result."""
    out = []
    for heading, part in (
        ("Inputs", record.inputs),
        ("Settings", record.settings),
        ("Result", record.result),
    ):
        rows: list[tuple[str, Any]] = []
        tables: list[tuple[str, list]] = []
        for key, value in part.items():
            if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
                tables.append((key, value))
            elif isinstance(value, dict):
                rows.extend((f"{key}.{k}", v) for k, v in value.items())
            elif isinstance(value, list):
                rows.append((key, ", ".join(_fmt(v) for v in value)))
            else:
                rows.append((key, value))
        out.append((heading, rows, tables))
    return out


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _meta(record: RunRecord) -> list[tuple[str, str]]:
    return [
        ("Function", record.function),
        ("labqc version", record.labqc_version),
        ("Date (UTC)", record.timestamp),
        ("Analyst", record.analyst or ""),
    ]


# --- Excel -------------------------------------------------------------------------------


def _sheet_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", "-", name).strip("'") or "Record"
    base = base[:28]
    candidate, n = base[:31], 2
    while candidate.lower() in used:
        candidate = f"{base} {n}"[:31]
        n += 1
    used.add(candidate.lower())
    return candidate


def to_excel(records: Sequence[RunRecord], path: PathOrFile) -> None:
    """Write records to an .xlsx workbook, one sheet per record (needs openpyxl)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError:  # pragma: no cover - depends on the environment
        raise ImportError('to_excel needs openpyxl: pip install "labqc[reports]"') from None
    if not records:
        raise ValueError("No records to write")
    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    bold = Font(bold=True)
    for record in records:
        ws = wb.create_sheet(_sheet_name(record.label(), used))
        ws.append([record.label()])
        ws["A1"].font = Font(bold=True, size=14)
        for key, value in _meta(record):
            ws.append([key, value])
        ws.append(["Method", record.method])
        for heading, rows, tables in _sections(record):
            if not rows and not tables:
                continue
            ws.append([])
            ws.append([heading])
            ws.cell(ws.max_row, 1).font = bold
            for key, value in rows:
                ws.append([key, value if isinstance(value, (int, float)) else _fmt(value)])
            for name, table in tables:
                columns = list(dict.fromkeys(k for row in table for k in row))
                ws.append([name])
                ws.cell(ws.max_row, 1).font = Font(italic=True)
                ws.append(columns)
                for cell in ws[ws.max_row]:
                    cell.font = bold
                for row in table:
                    ws.append([_cell(row.get(c)) for c in columns])
        ws.column_dimensions["A"].width = 32
        for col in "BCDEFGH":
            ws.column_dimensions[col].width = 16
    wb.save(path)


def _cell(value: Any) -> Any:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else _fmt(value)


# --- PDF ---------------------------------------------------------------------------------

_PDF_TEXT = str.maketrans(
    {
        "σ": "sigma ",
        "ν": "v",
        "μ": "u",
        "₂": "2",
        "³": "3",
        "²": "2",
        "≤": "<=",
        "≥": ">=",
        "−": "-",
        "–": "-",
        "∞": "inf",
        "√": "sqrt",
    }
)


def _pdf_text(value: Any) -> str:
    """Text the built-in PDF fonts can show, escaped for reportlab paragraphs."""
    text = _fmt(value).translate(_PDF_TEXT)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_pdf(record: RunRecord, path: PathOrFile) -> None:
    """Write one record as a PDF: title, meta data, method, inputs, result (needs reportlab)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:  # pragma: no cover - depends on the environment
        raise ImportError('to_pdf needs reportlab: pip install "labqc[reports]"') from None

    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small", fontSize=8, leading=10)
    grid = TableStyle(
        [
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
    )
    header = TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef2"))])

    def p(value: Any, style=small) -> Paragraph:
        return Paragraph(_pdf_text(value), style)

    story = [
        Paragraph(_pdf_text(record.label()), styles["Title"]),
        Table([[p(k), p(v)] for k, v in _meta(record)], colWidths=[40 * mm, 130 * mm], style=grid),
        Spacer(1, 4 * mm),
        Paragraph("Method", styles["Heading3"]),
        p(record.method or "-", styles["BodyText"]),
    ]
    for heading, rows, tables in _sections(record):
        if not rows and not tables:
            continue
        story += [Spacer(1, 3 * mm), Paragraph(heading, styles["Heading3"])]
        if rows:
            story.append(
                Table([[p(k), p(v)] for k, v in rows], colWidths=[60 * mm, 110 * mm], style=grid)
            )
        for name, table in tables:
            columns = list(dict.fromkeys(k for row in table for k in row))
            data = [[p(c) for c in columns]] + [[p(row.get(c)) for c in columns] for row in table]
            story += [Spacer(1, 2 * mm), p(name, styles["Italic"])]
            t = Table(data, repeatRows=1, style=grid)
            t.setStyle(header)
            story.append(t)
    story += [
        Spacer(1, 6 * mm),
        p(
            f"Calculated with labqc {record.labqc_version}, validated against published and "
            "hand-calculated reference cases. Validate it for your own use (ISO/IEC 17025 7.11)."
        ),
    ]
    SimpleDocTemplate(
        str(path) if isinstance(path, Path) else path,  # reportlab wants str or a file
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=record.label(),
        author=record.analyst or "",
        creator=f"labqc {record.labqc_version}",
    ).build(story)
