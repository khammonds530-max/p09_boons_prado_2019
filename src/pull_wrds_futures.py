
"""Pull historical commodity futures data from WRDS Datastream."""

from pathlib import Path

import wrds
import pandas as pd


OUTPUT_DIR = Path("_data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def pull_corn_futures(start_date="1959-07-01", end_date="2014-02-28"):
    """Download daily U.S. corn futures settlement prices."""

    db = wrds.Connection()

    try:
        query = """
            SELECT
                p.futcode,
                c.contrname,
                c.dsmnem,
                c.contrdate,
                c.lasttrddate,
                p.date_,
                p.settlement,
                p.volume,
                p.openinterest
            FROM tr_ds_fut.wrds_fut_contract p
            JOIN tr_ds_fut.wrds_contract_info c
                ON p.futcode = c.futcode
            WHERE c.contrname = 'CORN'
              AND c.exchtickersymb = 'C'
              AND c.isocurrcode = 'USD'
              AND p.date_ BETWEEN %s AND %s
              AND p.settlement IS NOT NULL
            ORDER BY p.date_, c.lasttrddate
        """

        df = db.raw_sql(query, params=(start_date, end_date))

    finally:
        db.close()

    output_path = OUTPUT_DIR / "corn_futures_historical.parquet"
    df.to_parquet(output_path, index=False)

    print(f"Downloaded {len(df):,} observations")
    print(f"Saved to {output_path}")

    return df


def pull_all_commodities():
    """Download historical futures data for all 21 commodities."""

    coverage = pd.read_csv("_data/wrds_commodity_coverage.csv")
    mappings = {
        "Corn": "CORN",
        "Wheat": "WHEAT",
        "Oats": "OATS",
        "Rough Rice": "RICE (ROUGH)",
        "Soybeans": "SOYBEANS",
        "Soybean Meal": "SOYBEAN MEAL",
        "Soybean Oil": "SOYBEAN OIL",
        "Crude Oil": "CRUDE OIL (LIGHT SWEET)",
        "Gasoline": "GASOLINE UNLEADED (NEW YORK)",
        "Heating Oil": "HEATING OIL (NEW YORK)",
        "Feeder Cattle": "CATTLE (FEEDER)",
        "Live Cattle": "CATTLE (LIVE)",
        "Lean Hogs": "HOGS (LEAN)",
        "Cotton": "COTTON #2",
        "Lumber": "LUMBER",
        "Gold": "GOLD (100 OZ)",
        "Silver": "SILVER (5000 OZ)",
        "Copper": "COPPER (HIGH GRADE)",
        "Coffee": "COFFEE 'C'",
        "Cocoa": "COCOA",
        "Orange Juice": "ORANGE JUICE (FCOJ-A)",
    }

    db = wrds.Connection()

    try:
        for row in coverage.itertuples(index=False):
            output = OUTPUT_DIR / f"{row.ticker}_futures.parquet"

            if output.exists():
                print(f"Skipping {row.commodity}: already downloaded")
                continue

            query = """
                SELECT
                    p.futcode,
                    c.contrname,
                    c.dsmnem,
                    c.contrdate,
                    c.lasttrddate,
                    p.date_,
                    p.settlement,
                    p.volume,
                    p.openinterest
                FROM tr_ds_fut.wrds_fut_contract p
                JOIN tr_ds_fut.wrds_contract_info c
                    ON p.futcode = c.futcode
                WHERE c.contrname = %s
                  AND c.exchtickersymb = %s
                  AND c.isocurrcode = 'USD'
                  AND p.date_ BETWEEN %s AND %s
                  AND p.settlement IS NOT NULL
                ORDER BY p.date_, c.lasttrddate
            """

            df = db.raw_sql(
                query,
                params=(
                    mappings[row.commodity],
                    row.ticker,
                    "1959-07-01",
                    "2014-02-28",
                ),
            )

            df.to_parquet(output, index=False)
            print(
                f"{row.commodity}: {len(df):,} observations saved",
                flush=True,
            )
    finally:
        db.close()

if __name__ == "__main__":
    pull_all_commodities()
