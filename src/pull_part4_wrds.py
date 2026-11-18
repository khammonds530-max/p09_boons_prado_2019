"""Pull the WRDS contract data used by Kayla, without changing her scripts.

The SQL uses her Datastream tables, join and USD/name/ticker restrictions.
Only each contract's last available observation per month is downloaded: these
are sufficient statistics for her month-end panel and same-contract returns.
Passwords are handled by libpq (.pgpass), never stored in project files.
"""

import argparse
import hashlib
import json
import os
from contextlib import ExitStack, closing
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from part4_config import DATA_DIR, PULL_END, PULL_START, UNIVERSE_FILE


def connection_parameters():
    """Read connection identity, never password, from env or a WRDS pgpass entry."""
    params = {"host": "wrds-pgdata.wharton.upenn.edu", "port": 9737, "dbname": "wrds"}
    user = os.getenv("WRDS_USERNAME") or os.getenv("PGUSER")
    pgpass = Path(os.getenv("PGPASSFILE", str(Path.home() / ".pgpass")))
    if pgpass.exists():
        for line in pgpass.read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split(":", 4)
            if len(parts) == 5 and "wrds" in parts[0].lower():
                host, port, dbname, entry_user, _ = parts
                params.update(
                    host=host,
                    port=int(port),
                    dbname="wrds" if dbname == "*" else dbname,
                )
                user = user or entry_user
                break
    if not user:
        raise RuntimeError(
            "Set WRDS_USERNAME and configure WRDS .pgpass before pulling data."
        )
    return dict(**params, user=user, connect_timeout=20, sslmode="require")


QUERY = """
SELECT DISTINCT ON (p.futcode, date_trunc('month', p.date_))
    p.futcode, c.contrname, c.dsmnem, c.contrdate, c.lasttrddate,
    p.date_, p.settlement, p.volume, p.openinterest
FROM tr_ds_fut.wrds_fut_contract p
JOIN tr_ds_fut.wrds_contract_info c ON p.futcode = c.futcode
WHERE c.contrname = %s AND c.exchtickersymb = %s
  AND c.isocurrcode = 'USD' AND p.date_ BETWEEN %s AND %s
  AND p.settlement IS NOT NULL
ORDER BY p.futcode, date_trunc('month', p.date_), p.date_ DESC
"""


def pull(force=False):
    """Download/cache each commodity and a dated, hashed provenance manifest."""
    import psycopg2

    raw_dir = DATA_DIR / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    universe = pd.read_csv(UNIVERSE_FILE)
    manifest_path = DATA_DIR / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    records = manifest.get("files", {})
    with ExitStack() as stack:
        connection = None
        for row in universe.itertuples(index=False):
            path = raw_dir / f"{row.ticker}_futures.parquet"
            spec = {
                "commodity": row.commodity,
                "ticker": row.ticker,
                "contrname": row.contrname,
                "start": PULL_START,
                "end": PULL_END,
                "query_sha256": hashlib.sha256(QUERY.encode()).hexdigest(),
            }
            previous = records.get(row.ticker, {})
            cached = path.exists() and all(
                previous.get(k) == v for k, v in spec.items()
            )
            if cached:
                cached = hashlib.sha256(path.read_bytes()).hexdigest() == previous.get(
                    "sha256"
                )
            if not force and cached:
                print(f"Cached: {row.commodity}", flush=True)
                continue
            if connection is None:
                connection = stack.enter_context(
                    closing(psycopg2.connect(**connection_parameters()))
                )
            with connection.cursor() as cursor:
                cursor.execute(QUERY, (row.contrname, row.ticker, PULL_START, PULL_END))
                frame = pd.DataFrame(
                    cursor.fetchall(), columns=[x[0] for x in cursor.description]
                )
            if frame.empty:
                raise RuntimeError(
                    f"No WRDS records for {row.commodity}; review mapping, do not silently omit it."
                )
            for column in ["settlement", "volume", "openinterest"]:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
            frame = frame.sort_values(["date_", "lasttrddate", "futcode"])
            temporary = path.with_suffix(".tmp.parquet")
            frame.to_parquet(temporary, index=False)
            temporary.replace(path)
            records[row.ticker] = dict(
                **spec,
                rows=len(frame),
                first_date=str(frame.date_.min()),
                last_date=str(frame.date_.max()),
                downloaded_utc=datetime.now(timezone.utc).isoformat(),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "source": "WRDS Datastream",
                        "frequency": "last observation per contract-month",
                        "files": records,
                    },
                    indent=2,
                )
            )
            print(
                f"Downloaded: {row.commodity}: {len(frame):,} contract-month observations",
                flush=True,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    pull(parser.parse_args().force)
