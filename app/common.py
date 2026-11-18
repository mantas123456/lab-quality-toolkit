"""Shared helpers for the labqc web app: page setup, demo data, errors, export.

No calculations live here or in the pages: every number comes from labqc.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
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


def footer() -> None:
    st.caption(
        f"labqc {labqc.__version__} · a calculation aid, not validated software: "
        "check results against your own procedures."
    )
