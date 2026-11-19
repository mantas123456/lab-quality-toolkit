"""Smoke test of the deployed (or locally served) browser build, with Playwright.

Skipped unless Playwright is installed and LABQC_WEB_URL points at the built app, e.g.

    python -m build --wheel && python web/build.py --wheel dist/labqc-*.whl --out site/app
    python -m http.server -d site 8000
    pip install playwright && playwright install chromium
    LABQC_WEB_URL=http://localhost:8000/app/ pytest tests/web/test_browser_smoke.py
"""

import os

import pytest

URL = os.environ.get("LABQC_WEB_URL")
playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not URL, reason="set LABQC_WEB_URL to the browser app")


def test_home_page_loads_in_the_browser():
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL)
        # Pyodide, the packages and labqc install on first load: allow a few minutes
        page.get_by_text("labqc: laboratory quality calculations").wait_for(timeout=300_000)
        page.get_by_text("Open an example directly").wait_for(timeout=60_000)
        assert "Traceback" not in page.content()
        browser.close()
