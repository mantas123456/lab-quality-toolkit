"""Build the browser version of the labqc app: Streamlit on Pyodide via stlite.

    python -m build --wheel
    python web/build.py --wheel dist/labqc-<version>-py3-none-any.whl --out site/app

The output folder is a static site: index.html, the app's files under app/ (the same pages
as the Streamlit Cloud app, unchanged) and the labqc wheel. Python runs in the visitor's
browser, so the page never sleeps and no data leaves the computer. The docs workflow puts it
on GitHub Pages under /app/, next to the documentation.

What does not work in the browser: PDF reports (reportlab is not installed); the Reports
page says so and still offers Excel and JSON.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
HERE = Path(__file__).resolve().parent

# stlite release used by the page (1.12.0: Streamlit 1.65, Pyodide 314, Python 3.14).
STLITE_VERSION = "1.12.0"
STLITE = f"https://cdn.jsdelivr.net/npm/@stlite/browser@{STLITE_VERSION}/build"

# Installed with micropip next to the labqc wheel; numpy, scipy and pandas come from
# Pyodide's own builds when micropip resolves labqc's dependencies.
REQUIREMENTS = ["plotly", "openpyxl"]


def app_files() -> list[Path]:
    """Every file the app reads at run time, relative to the repository root."""
    patterns = ["*.py", "pages/*.py", "demo_data/*.csv", "demo_data/*.json"]
    skip = {"make_demo_data.py"}  # builds the demo data from examples/; not needed at run time
    files = sorted({p for pat in patterns for p in APP.glob(pat) if p.name not in skip})
    return [p.relative_to(ROOT) for p in files]


def config(wheel_name: str) -> dict:
    files = {path.as_posix(): {"url": path.as_posix()} for path in app_files()}
    return {
        "entrypoint": "app/Home.py",
        "files": files,
        "requirements": REQUIREMENTS,
        "wheel": wheel_name,
    }


def index_html(cfg: dict) -> str:
    template = (HERE / "index.template.html").read_text(encoding="utf-8")
    return (
        template.replace("{{STLITE}}", STLITE)
        .replace("{{STLITE_VERSION}}", STLITE_VERSION)
        .replace("{{CONFIG}}", json.dumps(cfg, indent=2))
    )


def build(wheel: Path, out: Path) -> Path:
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise SystemExit(f"not a wheel file: {wheel}")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for rel in app_files():
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    shutil.copy2(wheel, out / wheel.name)
    (out / "index.html").write_text(index_html(config(wheel.name)), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wheel", type=Path, required=True, help="the labqc wheel to install")
    parser.add_argument("--out", type=Path, default=ROOT / "site" / "app")
    args = parser.parse_args()
    out = build(args.wheel, args.out)
    print(f"browser app with {len(app_files())} app files written to {out}")


if __name__ == "__main__":
    main()
