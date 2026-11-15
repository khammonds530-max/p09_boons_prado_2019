
"""Construct monthly four-nearby futures panels from WRDS data."""

from pathlib import Path

import pandas as pd


DATA_DIR = Path("_data")


def build_futures_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Select month-end prices and rank contracts expiring after t+2."""

    df = df.copy()
    df["date_"] = pd.to_datetime(df["date_"])
    df["lasttrddate"] = pd.to_datetime(df["lasttrddate"])
    df["month"] = df["date_"].dt.to_period("M")

    # Select one common observation date per commodity-month.
    month_end_dates = df.groupby("month")["date_"].transform("max")
    df = df[df["date_"] == month_end_dates].copy()

    # Paper's rule: expiration must be after month t+2.
    # Parse the contract month (MMYY format)
    df["contract_month"] = pd.to_datetime(
        df["contrdate"].astype(str).str.zfill(4),
        format="%m%y",
        errors="coerce"
    ).dt.to_period("M")

    # Exclude contracts expiring in t, t+1, or t+2
    df = df[df["contract_month"] > df["month"] + 2].copy()

    # Ensure contracts have not stopped trading
    df = df[df["lasttrddate"] >= df["date_"]].copy()


    # Rank eligible contracts by expiration.
    df = df.sort_values(["month", "lasttrddate", "futcode"])
    df["nearby_rank"] = df.groupby("month").cumcount() + 1

    # Retain the first four eligible contracts.
    df = df[df["nearby_rank"] <= 4].copy()

    assert not df.duplicated(["month", "nearby_rank"]).any()
    assert df.groupby("month")["date_"].nunique().eq(1).all()

    return df.reset_index(drop=True)


def build_all_panels():
    """Build monthly panels for all 21 commodities."""

    coverage = pd.read_csv(DATA_DIR / "wrds_commodity_coverage.csv")
    panels = []

    for row in coverage.itertuples(index=False):
        raw = pd.read_parquet(
            DATA_DIR / f"{row.ticker}_futures.parquet"
        )

        panel = build_futures_panel(raw)
        panel["commodity"] = row.commodity
        panel["ticker"] = row.ticker

        panels.append(panel)

        print(
            f"{row.commodity}: "
            f"{panel['month'].nunique()} months, "
            f"{len(panel):,} observations"
        )

    combined = pd.concat(panels, ignore_index=True)

    assert not combined.duplicated(
        ["commodity", "month", "nearby_rank"]
    ).any()

    output = DATA_DIR / "futures_monthly_panel.parquet"

    # Parquet does not support pandas Period dtype.
    combined["month"] = combined["month"].astype(str)

    combined.to_parquet(output, index=False)

    print(f"\nTotal observations: {len(combined):,}")
    print(f"Saved to {output}")


if __name__ == "__main__":
    build_all_panels()
