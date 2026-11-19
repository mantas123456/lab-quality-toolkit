"""Shared helpers for the labqc web app: page setup, demo data, errors, export.

No calculations live here or in the pages: every number comes from labqc.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from functools import cache
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "app" / "demo_data"

# Use the labqc source in this repository, so the app always matches the code it ships with
# (also on Streamlit Community Cloud, which runs the app straight from the repository).
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import labqc  # noqa: E402

STATUS_COLOURS = {"accept": "#2c6e8f", "warning": "#e0a100", "reject": "#c0392b"}
CLASS_COLOURS = {"satisfactory": "green", "questionable": "orange", "unsatisfactory": "red"}


# Example data sets that open from a link, e.g. .../Uncertainty_budget?example=moisture.
# name -> (page file, page label, what it shows). The page itself defines how to load it.
EXAMPLES: dict[str, tuple[str, str, str]] = {
    "moisture": (
        "pages/1_Uncertainty_budget.py", "Uncertainty budget",
        "oven-dry moisture budget (examples/moisture_uncertainty.py)",
    ),
    "moisture-shared-balance": (
        "pages/1_Uncertainty_budget.py", "Uncertainty budget",
        "the same budget with the three weighings correlated (r = 0.92, one balance)",
    ),
    "calibration": (
        "pages/2_Method_validation.py", "Method validation",
        "calibration line, LOD/LOQ, precision and recovery",
    ),
    "pt-round": (
        "pages/3_Proficiency_testing.py", "Proficiency testing",
        "z, zeta and En for one result, and a round of 15 labs",
    ),
    "pt-history": (
        "pages/3_Proficiency_testing.py", "Proficiency testing",
        "z-scores of 14 PT rounds with the warning signals",
    ),
    "westgard": (
        "pages/4_QC_charts.py", "QC charts",
        "Westgard rules with a shift from day 45 (examples/westgard_iqc.py)",
    ),
    "westgard-levels": (
        "pages/4_QC_charts.py", "QC charts",
        "Westgard rules across two control levels run together",
    ),
    "cusum": ("pages/4_QC_charts.py", "QC charts", "CUSUM chart of the same QC series"),
    "ewma": ("pages/4_QC_charts.py", "QC charts", "EWMA chart of the same QC series"),
    "boiler": (
        "pages/5_Emissions.py", "Emissions",
        "boiler test corrected to 10 % O2 (examples/boiler_emissions.py)",
    ),
    "topdown": (
        "pages/1_Uncertainty_budget.py", "Uncertainty budget",
        "top-down uncertainty from the QC series and six PT rounds (Nordtest TR 537)",
    ),
    "decision": (
        "pages/6_Decision_rules.py", "Decision rules",
        "lead in water near its limit, simple acceptance",
    ),
    "decision-guarded": (
        "pages/6_Decision_rules.py", "Decision rules",
        "the same result with a guard band w = U (non-binary statement)",
    ),
}  # fmt: skip


def example_url(name: str) -> str:
    """Relative link that opens the page of example `name` with it loaded.

    Streamlit serves pages/3_Proficiency_testing.py at /Proficiency_testing.
    """
    stem = Path(EXAMPLES[name][0]).stem
    return f"/{stem.split('_', 1)[1]}?example={name}"


def deep_link(page_file: str, loaders: Mapping[str, Callable[[], None]]) -> None:
    """Load the example named in ?example=<name>, once per name, before any widget is drawn.

    A name that belongs to another page gets a link to that page; an unknown name gets a
    plain warning with the list of names. Neither stops the page.
    """
    name = st.query_params.get("example")
    if not name:
        return
    name = name.strip().lower()
    if name in loaders:
        if st.session_state.get(f"_example_{page_file}") != name:
            loaders[name]()
            st.session_state[f"_example_{page_file}"] = name
        return
    if name in EXAMPLES:
        target, label, _ = EXAMPLES[name]
        st.warning(
            f"The example '{name}' belongs to the {label} page: "
            f"[open it there]({example_url(name)})."
        )
        return
    st.warning(
        f"There is no example called '{name}'. Examples you can open with ?example=: "
        + ", ".join(EXAMPLES)
        + "."
    )


CORR_COLUMNS = ("component_a", "component_b", "r")


def correlation_frame(correlation: Mapping[tuple[str, str], float] | None) -> pd.DataFrame:
    """A {(name, name): r} correlation as the app's editable table."""
    rows = [(a, b, r) for (a, b), r in (correlation or {}).items()]
    return pd.DataFrame(rows, columns=list(CORR_COLUMNS)).astype({"r": float})


def correlation_dict(table: pd.DataFrame) -> dict[tuple[str, str], float] | None:
    """The app's correlation table as the dict labqc.uncertainty.combine takes (None if empty).

    Rows with a blank cell are ignored; an r that is not a number raises ValueError.
    """
    out: dict[tuple[str, str], float] = {}
    for i, row in enumerate(table.dropna(how="any").itertuples(index=False), start=1):
        a, b, r = row
        try:
            out[(str(a), str(b))] = float(r)
        except (TypeError, ValueError):
            raise ValueError(f"Correlation row {i}: r = {r!r} is not a number") from None
    return out or None


def what_this_means(sentences: list[str]) -> None:
    """The plain-English box under a main result (sentences come from app/explain.py)."""
    if sentences:
        with st.container(border=True):
            st.markdown("**What this means**\n\n" + " ".join(sentences))


def page(title: str, intro: str) -> None:
    """Common page header."""
    st.set_page_config(page_title=f"{title} · labqc", page_icon="🧪", layout="wide")
    st.title(title)
    st.caption(intro)


def columns():
    """Inputs in the middle, results on the right (navigation sits on the left)."""
    return st.columns([1, 1.25], gap="large")


def export_header() -> None:
    st.divider()
    st.subheader("Export")


@cache
def examples() -> dict:
    """Scalar inputs of the worked examples (see demo_data/make_demo_data.py)."""
    return json.loads((DEMO / "examples.json").read_text(encoding="utf-8"))


def demo_table(name: str) -> pd.DataFrame:
    return pd.read_csv(DEMO / f"{name}.csv")


@contextmanager
def friendly_errors() -> Iterator[None]:
    """Show bad input as a plain message and stop the page, never as a traceback."""
    try:
        yield
    except ValueError as err:
        st.error(str(err))
        st.stop()
    except (TypeError, KeyError, ZeroDivisionError, ArithmeticError) as err:
        st.error(
            f"These inputs could not be calculated ({type(err).__name__}). "
            "Check that every cell holds a number and try again."
        )
        st.stop()


def parse_numbers(text: str, what: str) -> list[float]:
    """Numbers typed in a text box, separated by commas, spaces, semicolons or new lines."""
    parts = [p for p in text.replace(",", " ").replace(";", " ").split() if p]
    try:
        return [float(p) for p in parts]
    except ValueError:
        bad = next(p for p in parts if not _is_number(p))
        raise ValueError(f"{what}: {bad!r} is not a number") from None


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def add_record(make) -> None:
    """Button callback: build the RunRecord now and keep it for the Reports page."""
    record = make()
    st.session_state.setdefault("records", []).append(record)
    st.toast(f"Added to report: {record.label()}")


def report_button(make, key: str | None = None) -> None:
    """'Add to report' button; `make` returns a labqc.report.RunRecord of the current result.

    Give a `key` when a page has more than one (one per tab)."""
    st.button(
        "Add to report",
        key=key,
        on_click=add_record,
        args=(make,),
        help="Keep this result for the Reports page (PDF, Excel and JSON).",
    )


def footer() -> None:
    st.caption(
        f"labqc {labqc.__version__} · validated against reference cases; "
        "validate it for your own use before you report results."
    )
