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


def qc_overview_data() -> pd.DataFrame:
    """Daily control results of three methods at two levels for the QC overview page.

    Illustrative values. Ash/high ends with two results beyond +2 SD (2_2s, reject) and
    Moisture/low with one beyond +2 SD (1_2s, warning); the other series end in control.
    Chloride has an assigned target and SD; the others take their limits from 20 days.
    """
    import numpy as np

    from labqc.control_charts import limits_from_data

    rng = np.random.default_rng(21)
    dates = [f"2026-10-{d:02d}" for d in range(1, 31)]
    series = [
        ("Moisture (oven)", "low", 6.0, 0.08, False),
        ("Moisture (oven)", "high", 12.0, 0.15, False),
        ("Ash (550 °C)", "low", 0.80, 0.03, False),
        ("Ash (550 °C)", "high", 3.5, 0.09, False),
        ("Chloride (IC)", "low", 50.0, 1.2, True),
        ("Chloride (IC)", "high", 200.0, 4.0, True),
    ]
    frames = []
    for method, level, centre, sd, assigned in series:
        values = np.clip(rng.normal(centre, sd, 30), centre - 1.8 * sd, centre + 1.8 * sd)
        if not assigned:
            lim = limits_from_data(values[:20])
            values[20:] = np.clip(values[20:], lim.line(-1.5), lim.line(1.5))
            values[-4:-1] = lim.centre  # a quiet run-up to the last result
            if (method, level) == ("Ash (550 °C)", "high"):
                values[-2], values[-1] = lim.line(2.3), lim.line(2.5)
            if (method, level) == ("Moisture (oven)", "low"):
                values[-1] = lim.line(2.4)
        frame = pd.DataFrame(
            {"date": dates, "method": method, "level": level, "value": values.round(4)}
        )
        frame["target"] = centre if assigned else None
        frame["sd"] = sd if assigned else None
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def budget_templates() -> dict:
    """Ready-made uncertainty budgets for the Uncertainty page, with where each number
    usually comes from. Sensitivity coefficients come from labqc.uncertainty.propagate."""
    import moisture_uncertainty as moisture

    from labqc.uncertainty import Component, propagate

    def row(name, value, source, distribution="normal", k=1.0, sensitivity=1.0, dof=None,
            unit=""):  # fmt: skip
        return {
            "name": name, "value": value, "distribution": distribution, "k": k,
            "sensitivity": sensitivity, "dof": dof, "unit": unit, "source": source,
        }  # fmt: skip

    weighing = [
        row("Calibration certificate", 0.0002, "U at this load from the balance calibration "
            "certificate, with its k", k=2.0, unit="g"),
        row("Resolution (d = 0.1 mg)", 0.00005, "half the display step, d / 2",
            "rectangular", unit="g"),
        row("Repeatability", 0.00008, "SD of 10 weighings of a check weight; dof = n - 1",
            dof=9, unit="g"),
        row("Eccentricity", 0.0001, "largest off-centre difference in the calibration or "
            "your own check", "rectangular", unit="g"),
        row("Drift between calibrations", 0.0001, "change between the last two certificates "
            "or the daily check-weight record", "rectangular", unit="g"),
    ]  # fmt: skip

    # dilution: c = c0 * V1 / V2, 1000 mg/L stock, 1 mL pipette into a 100 mL flask
    def dilution(c0, v1, v2):
        return c0 * v1 / v2

    d_values = {"c0": 1000.0, "v1": 1.0, "v2": 100.0}
    d_inputs = {
        "c0": Component("Stock standard", 5.0, k=2),
        "v1": Component("Pipette 1 mL", 0.008, "triangular"),
        "v2": Component("Flask 100 mL", 0.10, "triangular"),
    }
    c_dil, d_res = propagate(dilution, d_values, d_inputs)
    sens = dict(zip(d_res.table["component"], d_res.table["c_i"], strict=True))
    dilution_rows = [
        row("Stock standard", 5.0, "certificate of the stock solution: U with its k", k=2.0,
            sensitivity=sens["Stock standard"], unit="mg/L"),
        row("Pipette 1 mL (class A)", 0.008, "tolerance printed on the pipette (± mL), "
            "triangular as Eurachem suggests", "triangular", sensitivity=sens["Pipette 1 mL"],
            unit="mL"),
        row("Pipetting repeatability", 0.002, "SD of 10 weighed deliveries of water; "
            "dof = n - 1", sensitivity=sens["Pipette 1 mL"], dof=9, unit="mL"),
        row("Flask 100 mL (class A)", 0.10, "tolerance printed on the flask (± mL)",
            "triangular", sensitivity=sens["Flask 100 mL"], unit="mL"),
        row("Temperature (± 4 °C)", 100.0 * 2.1e-4 * 4, "flask volume x expansion of water "
            "(2.1e-4 /°C) x the lab's temperature range", "rectangular",
            sensitivity=sens["Flask 100 mL"], unit="mL"),
    ]  # fmt: skip

    by_name = moisture.result.table.set_index("component")
    moisture_rows = [
        row(name, by_name.loc[name, "u_i"], "balance calibration and resolution combined "
            "for this weighing (see Weighing on a balance)",
            sensitivity=by_name.loc[name, "c_i"], unit="g")
        for name in (c.name for c in moisture.inputs.values())
    ] + [
        row(moisture.repeat.name, moisture.repeat.value, "SD of the test portions / sqrt(n); "
            "dof = n - 1", dof=moisture.repeat.dof, unit="%"),
    ]  # fmt: skip

    # O2 correction: C_ref = C (20.9 - O2_ref) / (20.9 - O2_m), CO 400 mg/m3 at 12.8 % O2
    def o2(c, o2_m):
        return c * (20.9 - 10.0) / (20.9 - o2_m)

    o_values = {"c": 400.0, "o2_m": 12.8}
    o_inputs = {
        "c": Component("Analyser calibration", 8.0, k=2),
        "o2_m": Component("O2 analyser", 0.2, k=2),
    }
    c_ref, o_res = propagate(o2, o_values, o_inputs)
    o_sens = dict(zip(o_res.table["component"], o_res.table["c_i"], strict=True))
    o2_rows = [
        row("Analyser calibration", 8.0, "span-gas certificate and calibration: U as 2 % of "
            "the reading, with its k", k=2.0, sensitivity=o_sens["Analyser calibration"],
            unit="mg/m3"),
        row("Lack of fit and drift", 8.0, "QAL or monthly check: largest deviation, as a "
            "half-width", "rectangular", sensitivity=o_sens["Analyser calibration"],
            unit="mg/m3"),
        row("Repeatability of the reading", 4.0, "SD of 10 one-minute means at steady load; "
            "dof = n - 1", sensitivity=o_sens["Analyser calibration"], dof=9, unit="mg/m3"),
        row("O2 analyser", 0.2, "O2 analyser calibration: U in % O2 by volume, with its k",
            k=2.0, sensitivity=o_sens["O2 analyser"], unit="% O2"),
    ]  # fmt: skip

    return {
        "weighing": {
            "title": "Weighing on a balance",
            "y": 25.4312, "unit": "g",
            "note": "One weighing of about 25 g on a 0.1 mg balance.",
            "rows": weighing,
        },
        "dilution": {
            "title": "Volumetric dilution",
            "y": c_dil, "unit": "mg/L",
            "note": "c = c0 x V1 / V2: 1000 mg/L stock, 1 mL into 100 mL.",
            "rows": dilution_rows,
        },
        "moisture": {
            "title": "Oven-dry moisture",
            "y": moisture.M, "unit": "%",
            "note": "M = (m2 - m3) / (m2 - m1) x 100, as in examples/moisture_uncertainty.py.",
            "rows": moisture_rows,
        },
        "o2": {
            "title": "O2 reference correction",
            "y": c_ref, "unit": "mg/m3",
            "note": "C_ref = C (20.9 - 10) / (20.9 - O2): CO 400 mg/m3 at 12.8 % O2, to 10 % O2.",
            "rows": o2_rows,
        },
    }  # fmt: skip


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

    # 2b. a second control level run with the same samples: low level, with the same shift
    #     in SD units from day 45, so the two-level Westgard rules see it on both materials
    import numpy as np

    rng = np.random.default_rng(3)
    low = rng.normal(10.0, 0.25, 50)
    low[44:] += 0.45
    qc_levels = pd.concat(
        [
            pd.DataFrame({"day": qc["day"], "level": "low", "value": low}),
            pd.DataFrame({"day": qc["day"], "level": "high", "value": qc["value"]}),
        ],
        ignore_index=True,
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

    # PT history: z-scores of 14 quarterly rounds (the pt_history validation case)
    pt_hist = pd.DataFrame(
        {
            "date": [f"{2023 + q // 4}-{3 * (q % 4) + 1:02d}-15" for q in range(14)],
            "z": [0.3, -0.5, 2.4, -2.2, 0.1, 0.4, 0.8, 0.2, 1.1, 0.6, 0.3, 0.9, 0.5, -3.1],
        }
    )

    # top-down (Nordtest): the in-control part of the QC series (before the shift on day 45)
    topdown_qc = pd.DataFrame({"day": qc["day"][:44], "value": qc["value"][:44]})
    # six PT rounds for the same method (illustrative), with the assigned values' u
    topdown_pt = pd.DataFrame(
        {
            "round": [f"2025-{m:02d}" for m in (2, 4, 6, 8, 10, 12)],
            "result": [48.9, 52.3, 47.1, 50.6, 55.2, 49.4],
            "assigned": [48.2, 51.0, 47.9, 50.1, 54.0, 48.6],
            "u_assigned": [0.6, 0.7, 0.6, 0.6, 0.8, 0.6],
        }
    )

    # the three weighings share one balance calibration (examples/monte_carlo_vs_gum.py)
    u_cal, u_res = 0.001, 0.0005 / 3**0.5
    r_shared = u_cal**2 / (u_cal**2 + u_res**2)

    scalars = {
        "moisture": {"y": moisture.M, "unit": "%", "r_shared_balance": r_shared},
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
        "decision": {
            "value": 9.2,
            "U": 1.5,
            "k": 2.0,
            "upper": 10.0,
            "unit": "µg/L",
            "what": "lead in drinking water against a limit of 10 µg/L (illustrative values)",
        },
        "templates": budget_templates(),
        "topdown_crm": {"results": [50.9, 51.4, 50.2, 51.8, 50.7], "certified": 50.0, "u": 0.4},
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
        "qc_levels": qc_levels,
        "pt_history": pt_hist,
        "topdown_qc": topdown_qc,
        "topdown_pt": topdown_pt,
        "qc_overview": qc_overview_data(),
    }
    return tables, scalars


def csv_text(df: pd.DataFrame) -> str:
    return df.to_csv(index=False, float_format="%.17g", lineterminator="\n")


def json_text(scalars: dict) -> str:
    return json.dumps(scalars, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    tables, scalars = build()
    for name, df in tables.items():
        (HERE / f"{name}.csv").write_text(csv_text(df), encoding="utf-8")
    (HERE / "examples.json").write_text(json_text(scalars), encoding="utf-8")
    print(f"wrote {len(tables)} tables and examples.json to {HERE}")
