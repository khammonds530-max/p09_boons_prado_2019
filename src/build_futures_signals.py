
"""Calculate futures characteristics for the basis-momentum replication."""

from pathlib import Path
import pandas as pd

DATA_DIR = Path("_data")


def calculate_basis(df):
    """Calculate basis using first- and second-nearby prices."""

    prices = df.pivot(
        index=["commodity", "month"],
        columns="nearby_rank",
        values="settlement",
    )

    # First- and second-nearby settlement prices
    first = prices[1]
    second = prices[2]

    # Basis = F2 / F1 - 1
    basis = (second / first - 1).where(
        (first > 0) & (second > 0)
    )

    result = basis.rename("basis").reset_index()

    return result


def calculate_momentum(df):
    """Calculate trailing 12-month compounded first-nearby returns."""

    first = df[df["nearby_rank"] == 1].copy()

    first["month"] = pd.PeriodIndex(first["month"], freq="M")
    first = first.sort_values(["commodity", "month"])

    # Forward return from month t to month t+1
    # becomes known at the end of month t+1.
    first["realized_return"] = (
        first.groupby("commodity")["monthly_return"].shift(1)
    )

    # Require 12 consecutive monthly observations
    first["month_number"] = (
        first["month"].dt.year * 12 + first["month"].dt.month
    )

    first["momentum"] = (
        first.groupby("commodity")["realized_return"]
        .transform(
            lambda s: (1 + s).rolling(
                window=12, min_periods=12
            ).apply(lambda x: x.prod(), raw=True) - 1
        )
    )

    first["previous_month_number"] = (
        first.groupby("commodity")["month_number"].shift(11)
    )

    first.loc[
        first["month_number"] - first["previous_month_number"] != 11,
        "momentum"
    ] = float("nan")

    return first[["commodity", "month", "momentum"]]


def calculate_basis_momentum(df):
    """Calculate trailing 12-month first-minus-second nearby returns."""

    selected = df[df["nearby_rank"].isin([1, 2])].copy()

    selected["month"] = pd.PeriodIndex(
        selected["month"], freq="M"
    )

    selected = selected.sort_values(
        ["commodity", "nearby_rank", "month"]
    )

    # Move forward returns to the month they become known
    selected["realized_return"] = (
        selected.groupby(
            ["commodity", "nearby_rank"]
        )["monthly_return"].shift(1)
    )

    selected["month_number"] = (
        selected["month"].dt.year * 12
        + selected["month"].dt.month
    )

    # Calculate trailing compounded returns for each nearby rank
    selected["trailing_return"] = (
        selected.groupby(
            ["commodity", "nearby_rank"]
        )["realized_return"]
        .transform(
            lambda s: (1 + s).rolling(
                window=12, min_periods=12
            ).apply(lambda x: x.prod(), raw=True) - 1
        )
    )

    # Require 12 consecutive calendar months
    selected["previous_month_number"] = (
        selected.groupby(
            ["commodity", "nearby_rank"]
        )["month_number"].shift(11)
    )

    selected.loc[
        selected["month_number"]
        - selected["previous_month_number"] != 11,
        "trailing_return"
    ] = float("nan")

    # Put first- and second-nearby returns side by side
    wide = selected.pivot(
        index=["commodity", "month"],
        columns="nearby_rank",
        values="trailing_return",
    )

    wide["basis_momentum"] = wide[1] - wide[2]

    return wide[["basis_momentum"]].reset_index()


if __name__ == "__main__":
    df = pd.read_parquet(
        DATA_DIR / "futures_monthly_returns.parquet"
    )

    basis = calculate_basis(df)
    momentum = calculate_momentum(df)
    basis_momentum = calculate_basis_momentum(df)

    # Ensure consistent month types
    for signals in [basis, momentum, basis_momentum]:
        signals["month"] = pd.PeriodIndex(
            signals["month"], freq="M"
        )

    combined = (
        basis
        .merge(
            momentum,
            on=["commodity", "month"],
            validate="one_to_one"
        )
        .merge(
            basis_momentum,
            on=["commodity", "month"],
            validate="one_to_one"
        )
    )

    assert not combined.duplicated(
        ["commodity", "month"]
    ).any()

    print("Total commodity-months:", len(combined))

    print("\nValid observations per signal:")
    print(
        combined[
            ["basis", "momentum", "basis_momentum"]
        ].notna().sum()
    )

    complete = combined.dropna(
        subset=["basis", "momentum", "basis_momentum"]
    )

    print("\nMonths with all three signals:", len(complete))

    print("\nComplete observations by commodity:")
    print(
        complete.groupby("commodity")
        .size()
        .to_string()
    )

    # Save the full dataset, including missing observations
    combined["month"] = combined["month"].astype(str)

    output = DATA_DIR / "futures_signals.parquet"
    combined.to_parquet(output, index=False)

    print("\nSaved to:", output)