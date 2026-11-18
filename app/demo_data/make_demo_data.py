"""Write the app's demo data from the worked examples, so the app and the library agree.

Run from the repository root after changing an example:

    python app/demo_data/make_demo_data.py

tests/app checks that these files are up to date.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
for path in (ROOT / "src", ROOT / "examples"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def build() -> tuple[dict[str, pd.DataFrame], dict]:
    """Return the demo tables and the scalar example inputs."""
    import boiler_emissions
    import moisture_uncertainty as moisture
    import westgard_iqc

    # 1. moisture budget: the components propagate() built, in input order
    by_name = moisture.result.table.set_index("component")
    weighings = [c.name for c in moisture.inputs.values()]
    rows = [
        {
            "name": name,
            "value": by_name.loc[name, "u_i"],
            "distribution": "normal",
            "k": 1.0,
            "sensitivity": by_name.loc[name, "c_i"],
            "dof": None,
            "unit": "g",
        }
        for name in weighings
    ]
    rows.append(
        {
            "name": moisture.repeat.name,
            "value": moisture.repeat.value,
            "distribution": "normal",
            "k": 1.0,
            "sensitivity": 1.0,
            "dof": moisture.repeat.dof,
            "unit": "%",
        }
    )
    budget = pd.DataFrame(rows)

    # 2. daily QC: 20 baseline days, then the 30 routine days with the shift from day 45
    qc = pd.DataFrame(
        {
            "day": range(1, 51),
            "value": [*westgard_iqc.baseline, *westgard_iqc.routine],
        }
    )

    # 3. boiler readings
    readings = pd.DataFrame(
        {
            "gas": list(boiler_emissions.readings),
            "value": list(boiler_emissions.readings.values()),
            "unit": "ppm",
            "limit": [boiler_emissions.limit_mg_m3.get(g) for g in boiler_emissions.readings],
        }
    )

    # validation and PT have no script in examples/; these are small illustrative sets
    calibration = pd.DataFrame(
        {
            "concentration": [1, 1, 2, 2, 5, 5, 10, 10],
            "signal": [0.11, 0.10, 0.21, 0.19, 0.52, 0.49, 1.08, 0.97],
        }
    )
    pt_round = pd.DataFrame(
        {
            "lab": [f"Lab {i:02d}" for i in range(1, 16)],
            "result": [
                10.12, 9.95, 10.31, 10.04, 9.88, 10.21, 10.09, 9.79,
                10.15, 11.65, 10.02, 9.97, 10.26, 8.70, 10.07,
            ],
        }
    )  # fmt: skip

    scalars = {
        "moisture": {"y": moisture.M, "unit": "%"},
        "qc": {"baseline_points": len(westgard_iqc.baseline)},
        "emissions": {
            "o2_measured": boiler_emissions.o2_measured,
            "o2_ref": 10.0,
            "water_vol_fraction": 0.0,
            "t_c": 0.0,
            "p_kpa": 101.325,
        },
        "validation": {
            "replicates": [50.4, 50.7, 49.1, 49.0, 51.1],
            "recovery": {"measured": 14.5, "unspiked": 5.0, "added": 10.0},
        },
        "pt": {
            "x": 10.75,
            "assigned": 10.0,
            "sigma_pt": 0.3,
            "u_x": 0.2,
            "u_assigned": 0.1,
            "U_x": 0.4,
            "U_assigned": 0.2,
        },
    }
    tables = {
        "moisture_budget": budget,
        "qc_daily": qc,
        "boiler_readings": readings,
        "calibration": calibration,
        "pt_round": pt_round,
    }
    return tables, scalars


def csv_text(df: pd.DataFrame) -> str:
    return df.to_csv(index=False, float_format="%.17g", lineterminator="\n")


def json_text(scalars: dict) -> str:
    return json.dumps(scalars, indent=2) + "\n"


if __name__ == "__main__":
    tables, scalars = build()
    for name, df in tables.items():
        (HERE / f"{name}.csv").write_text(csv_text(df), encoding="utf-8")
    (HERE / "examples.json").write_text(json_text(scalars), encoding="utf-8")
    print(f"wrote {len(tables)} tables and examples.json to {HERE}")
