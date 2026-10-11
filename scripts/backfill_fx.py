"""Backfill BRL→USD FX rates for the full Olist date range (2016-09-01 to 2018-10-31).

Writes one JSON file per trading day to data/fx_cache/ via Frankfurter API.
Already-cached dates are skipped. Run once before `make dbt-build`.

Usage:
    python scripts/backfill_fx.py
    python scripts/backfill_fx.py --start 2017-01-01 --end 2017-12-31
"""
from __future__ import annotations

import argparse
from datetime import date

from ingestion.fx_client import FXClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill BRL/USD FX rates")
    parser.add_argument("--start", default="2016-09-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end",   default="2018-10-31", help="End date YYYY-MM-DD")
    parser.add_argument("--delay", type=float, default=0.25,
                        help="Seconds between API calls (default: 0.25)")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)

    print(f"Backfilling BRL/USD rates {start} → {end} …")
    client = FXClient()
    rates = client.backfill_date_range(start, end, delay_s=args.delay)
    print(f"✅  {len(rates)} unique trading days cached in {client.cache_dir}")


if __name__ == "__main__":
    main()
