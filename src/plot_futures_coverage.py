
"""Plot historical data coverage for all 21 commodities."""

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

DATA_DIR = Path("_data")
OUTPUT_DIR = Path("_output")
OUTPUT_DIR.mkdir(exist_ok=True)

df = pd.read_parquet(DATA_DIR / "futures_signals.parquet")

signals = ["basis", "momentum", "basis_momentum"]

df["month"] = pd.to_datetime(df["month"])
df["complete"] = df[signals].notna().all(axis=1)

commodities = sorted(df["commodity"].unique())

fig, ax = plt.subplots(figsize=(13, 9))

for i, commodity in enumerate(commodities):
    subset = df[df["commodity"] == commodity].sort_values("month")

    # All available commodity-month observations
    ax.scatter(
        subset["month"],
        [i] * len(subset),
        color="lightgray",
        marker="s",
        s=14,
        label="Available futures data" if i == 0 else None,
    )

    # Months with all three signals available
    complete = subset[subset["complete"]]

    ax.scatter(
        complete["month"],
        [i] * len(complete),
        color="steelblue",
        marker="s",
        s=14,
        label="All three signals available" if i == 0 else None,
    )

ax.set_yticks(range(len(commodities)))
ax.set_yticklabels(commodities)
ax.invert_yaxis()

ax.set_xlabel("Year")
ax.set_title("Historical Futures Data and Signal Coverage (1973–2014)")

ax.legend(loc="lower right")
ax.grid(axis="x", alpha=0.2)

plt.tight_layout()

output = OUTPUT_DIR / "futures_data_coverage.png"
plt.savefig(output, dpi=300, bbox_inches="tight")
plt.close()

print("Saved figure to:", output)
