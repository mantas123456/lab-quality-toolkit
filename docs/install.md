# Install

labqc needs Python 3.10 or newer. Its only dependencies are numpy, pandas and scipy.

```bash
pip install labqc
```

To work on labqc itself, clone the repository and install it in editable mode with the
development tools:

```bash
git clone https://github.com/mantas123456/lab-quality-toolkit
cd lab-quality-toolkit
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows; on Linux or macOS: source .venv/bin/activate
pip install -e ".[dev]"             # adds pytest, ruff, matplotlib, build, twine
pytest
```

To build this documentation locally:

```bash
pip install -e ".[docs]"
mkdocs serve                        # then open http://127.0.0.1:8000
```
