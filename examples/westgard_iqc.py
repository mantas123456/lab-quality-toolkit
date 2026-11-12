"""Internal quality control: a control material run daily, with a step shift on day 45."""

import matplotlib.pyplot as plt
import numpy as np

from labqc.control_charts import limits_from_data, westgard

rng = np.random.default_rng(7)
baseline = rng.normal(50.0, 0.8, 20)  # 20 days to set the limits
routine = rng.normal(50.0, 0.8, 30)
routine[24:] += 1.4  # a +1.4 shift from day 45 (e.g. a new calibrant lot)

limits = limits_from_data(baseline)
table = westgard(routine, limits)
table.index = range(21, 21 + len(routine))

if __name__ == "__main__":
    print(f"Centre {limits.centre:.2f}, SD {limits.sd:.2f}\n")
    flagged = table[table["status"] != "accept"]
    rules = flagged.drop(columns=["value", "z", "status"])
    flagged = flagged.assign(rules=rules.apply(lambda r: ", ".join(r.index[r]), axis=1))
    print(flagged[["value", "z", "status", "rules"]].to_string())

    fig, ax = plt.subplots(figsize=(8, 3.6))
    days = list(range(1, 21)) + list(table.index)
    ax.plot(days, list(baseline) + list(routine), "-", color="#888", linewidth=0.8)
    ax.scatter(range(1, 21), baseline, s=14, color="#888", label="Baseline")
    colors = {"accept": "#2c6e8f", "warning": "#e0a100", "reject": "#c0392b"}
    for s, c in colors.items():
        d = table[table["status"] == s]
        ax.scatter(d.index, d["value"], s=22, color=c, label=s.capitalize(), zorder=3)
    for n, ls in [(0, "-"), (2, "--"), (-2, "--"), (3, ":"), (-3, ":")]:
        ax.axhline(limits.line(n), color="black", linestyle=ls, linewidth=0.7)
    ax.axvline(20.5, color="#bbb", linewidth=0.8)
    ax.set_xlabel("Day")
    ax.set_ylabel("Control result (mg/kg)")
    ax.set_title("Levey-Jennings chart with Westgard rules", loc="left")
    ax.legend(frameon=False, fontsize=8, ncol=4, loc="upper left")
    fig.tight_layout()
    fig.savefig("examples/westgard_chart.png", dpi=130)
