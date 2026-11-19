"""The browser build (web/build.py): every app file is shipped and listed, with the wheel."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "web"))
import build  # noqa: E402


@pytest.fixture
def site(tmp_path):
    wheel = tmp_path / "labqc-9.9.9-py3-none-any.whl"
    wheel.write_bytes(b"not really a wheel")
    return build.build(wheel, tmp_path / "site" / "app")


def config_of(site: Path) -> dict:
    html = (site / "index.html").read_text(encoding="utf-8")
    match = re.search(r'id="labqc-config">\s*(\{.*?\})\s*</script>', html, re.S)
    return json.loads(match.group(1))


def test_every_page_and_demo_file_is_shipped(site):
    cfg = config_of(site)
    pages = {p.relative_to(ROOT).as_posix() for p in (ROOT / "app" / "pages").glob("*.py")}
    demo = {p.relative_to(ROOT).as_posix() for p in (ROOT / "app" / "demo_data").glob("*.csv")}
    expected = pages | demo | {"app/Home.py", "app/common.py", "app/explain.py"}
    assert expected <= set(cfg["files"])
    for path in cfg["files"]:
        assert (site / path).is_file(), path
    assert cfg["entrypoint"] == "app/Home.py"


def test_wheel_and_pinned_stlite(site):
    cfg = config_of(site)
    assert cfg["wheel"] == "labqc-9.9.9-py3-none-any.whl"
    assert (site / cfg["wheel"]).is_file()
    html = (site / "index.html").read_text(encoding="utf-8")
    assert f"@stlite/browser@{build.STLITE_VERSION}/build/stlite.js" in html
    assert re.fullmatch(r"\d+\.\d+\.\d+", build.STLITE_VERSION)  # an exact version
    assert "{{" not in html


def test_no_app_file_needs_a_package_missing_in_the_browser():
    """reportlab is not installed in the browser: only labqc.report may import it, lazily."""
    for rel in build.app_files():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "import reportlab" not in text and "from reportlab" not in text, rel
        assert "streamlit.testing" not in text, rel  # stlite's Streamlit leaves it out


def test_rejects_a_missing_wheel(tmp_path):
    with pytest.raises(SystemExit, match="not a wheel"):
        build.build(tmp_path / "missing.whl", tmp_path / "out")
