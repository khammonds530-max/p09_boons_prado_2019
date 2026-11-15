
"""Calculate same-contract monthly futures returns from WRDS data."""

from pathlib import Path
import pandas as pd

DATA_DIR = Path("_data")


def build_monthly_returns(raw, panel):
    """Match selected contracts to their next-month settlement prices."""
    raw = raw.copy()
    raw["date_"] = pd.to_datetime(raw["date_"])
    raw["month"] = raw["date_"].dt.to_period("M")

    # Last available settlement for each contract in each month
    monthly_prices = (
        raw.sort_values("date_")
        .groupby(["futcode", "month"], as_index=False)
        .tail(1)
        [["futcode", "month", "settlement"]]
        .rename(columns={"settlement": "next_settlement"})
    )

    panel = panel.copy()
    panel["month"] = pd.PeriodIndex(panel["month"], freq="M")
    panel["next_month"] = panel["month"] + 1

    # Match by exact contract, not nearby rank
    result = panel.merge(
        monthly_prices,
        left_on=["futcode", "next_month"],
        right_on=["futcode", "month"],
        how="left",
        suffixes=("", "_matched"),
        validate="many_to_one",
    )

    # Identify the final trading date for each commodity-month
    month_end_dates = raw.groupby("month")["date_"].max()

    # Identify the actual date of each matched contract price
    contract_end_dates = (
        raw.groupby(["futcode", "month"])["date_"]
        .max()
        .rename("next_price_date")
        .reset_index()
    )

    result = result.merge(
        contract_end_dates,
        left_on=["futcode", "next_month"],
        right_on=["futcode", "month"],
        how="left",
        suffixes=("", "_date"),
        validate="many_to_one",
    )

    result["expected_next_date"] = result["next_month"].map(
        month_end_dates
    )

    # Only calculate returns when both prices represent month-end
    valid_next_price = (
        result["next_price_date"] == result["expected_next_date"]
    )

    result["monthly_return"] = (
        result["next_settlement"] / result["settlement"] - 1
    ).where(valid_next_price)

    return result

if __name__ == "__main__":
    coverage = pd.read_csv(DATA_DIR / "wrds_commodity_coverage.csv")
    panel = pd.read_parquet(DATA_DIR / "futures_monthly_panel.parquet")

    all_returns = []

    for row in coverage.itertuples(index=False):
        raw = pd.read_parquet(
            DATA_DIR / f"{row.ticker}_futures.parquet"
        )

        commodity_panel = panel[
            panel["commodity"] == row.commodity
        ].copy()

        result = build_monthly_returns(raw, commodity_panel)
        all_returns.append(result)

        calculated = result["monthly_return"].notna().sum()
        missing = result["monthly_return"].isna().sum()

        print(
            f"{row.commodity}: "
            f"{calculated:,} returns, {missing} missing"
        )

    combined = pd.concat(all_returns, ignore_index=True)

    output = DATA_DIR / "futures_monthly_returns.parquet"

    # Parquet-compatible month columns
    combined["month"] = combined["month"].astype(str)
    combined["next_month"] = combined["next_month"].astype(str)

    combined.to_parquet(output, index=False)

    print(f"\nTotal observations: {len(combined):,}")
    print(
        "Total calculated returns:",
        combined["monthly_return"].notna().sum()
    )
    print("Saved to:", output)

