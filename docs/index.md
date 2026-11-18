# labqc

Laboratory quality calculations in Python. The calculations an ISO/IEC 17025 laboratory
does every week, usually in spreadsheets, written as small, tested Python functions:

--8<-- "README.md:modules"

!!! note "Validated against reference cases"
    labqc 1.0 passes 91 reference cases with stated tolerances and sources: see the
    [validation report](validation.md) and [change control](change_control.md). A laboratory
    must still validate it for its own intended use before reporting results
    (ISO/IEC 17025 clause 7.11.2).

- **[Try the web app](https://lab-quality-toolkit-3go33hyzzwjhwpktn8tles.streamlit.app)** in the browser: every module, with example data, no installation.
- [Install](install.md) and [Quick start](quickstart.md) get you to a first uncertainty budget.
- The **API reference** documents every function, generated from the source code.
- [Worked examples](examples.md) show real lab cases with their output.
