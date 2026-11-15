
"""Build the commodity overview table for the Basis-Momentum project."""

from pathlib import Path

import pandas as pd

DATA_DIR = Path("_data")
OUTPUT_DIR = Path("_output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load existing monthly futures returns
df = pd.read_parquet(DATA_DIR / "futures_monthly_returns.parquet")

# Keep first- and second-nearby contracts
df = df[df["nearby_rank"].isin([1, 2])].copy()

# One row per commodity-month, with both nearby returns
returns = df.pivot(
    index=["commodity", "month"],
    columns="nearby_rank",
    values="monthly_return",
).rename(columns={1: "nearby_return", 2: "second_return"})

returns = returns.reset_index()

# Spreading return: long first-nearby, short second-nearby
returns["spreading_return"] = (
    returns["nearby_return"] - returns["second_return"]
)

# Summarize each commodity
overview = (
    returns.groupby("commodity")
    .agg(
        sample_start=("month", "min"),
        observations=("nearby_return", "count"),
        mean_nearby_return=("nearby_return", "mean"),
        mean_spreading_return=("spreading_return", "mean"),
    )
    .reset_index()
)

# Convert returns to percentages
overview["mean_nearby_return"] *= 100
overview["mean_spreading_return"] *= 100

exchange_map = {
    "Corn": "CBOT",
    "Wheat": "CBOT",
    "Oats": "CBOT",
    "Rough Rice": "CBOT",
    "Soybeans": "CBOT",
    "Soybean Meal": "CBOT",
    "Soybean Oil": "CBOT",
    "Feeder Cattle": "CME",
    "Live Cattle": "CME",
    "Lean Hogs": "CME",
    "Lumber": "CME",
    "Crude Oil": "NYMEX",
    "Gasoline": "NYMEX",
    "Heating Oil": "NYMEX",
    "Gold": "COMEX",
    "Silver": "COMEX",
    "Copper": "COMEX",
    "Coffee": "NYBOT/ICE",
    "Cocoa": "NYBOT/ICE",
    "Cotton": "NYBOT/ICE",
    "Orange Juice": "NYBOT/ICE",
}

overview.insert(1, "exchange", overview["commodity"].map(exchange_map))

overview = overview.rename(
    columns={
        "commodity": "Commodity",
        "exchange": "Exchange",
        "sample_start": "Sample Start",
        "observations": "Months",
        "mean_nearby_return": "Mean Nearby Return (%)",
        "mean_spreading_return": "Mean Spreading Return (%)",
    }
)

overview = overview.sort_values("Commodity")

output = OUTPUT_DIR / "commodity_overview.csv"
overview.to_csv(output, index=False)

print(overview.round(3).to_string(index=False))
print(f"\nSaved to {output}")
print(f"Total commodities: {len(overview)}")
