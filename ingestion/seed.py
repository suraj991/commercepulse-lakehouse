"""Seed PostgreSQL with Olist CSV data.

Creates one schema per logical group and loads each CSV as a table.
Idempotent: drops and recreates tables on each run (replace strategy).

Usage:
    python -m ingestion.seed --data-dir data/raw/olist
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from ingestion.config import POSTGRES_URL, RAW_DATA_DIR

# Mapping from CSV stem → (schema, table_name)
TABLE_MAP: dict[str, tuple[str, str]] = {
    "olist_orders_dataset": ("olist", "orders"),
    "olist_order_items_dataset": ("olist", "order_items"),
    "olist_order_payments_dataset": ("olist", "order_payments"),
    "olist_order_reviews_dataset": ("olist", "order_reviews"),
    "olist_customers_dataset": ("olist", "customers"),
    "olist_sellers_dataset": ("olist", "sellers"),
    "olist_products_dataset": ("olist", "products"),
    "olist_geolocation_dataset": ("olist", "geolocation"),
    "product_category_name_translation": ("olist", "product_category_translations"),
    "olist_marketing_qualified_leads_dataset": ("marketing", "mql"),
    "olist_closed_deals_dataset": ("marketing", "closed_deals"),
}


def seed(data_dir: Path = RAW_DATA_DIR) -> dict[str, int]:
    """Load all Olist CSVs into PostgreSQL. Returns {table: row_count}."""
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)

    # Ensure schemas exist
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS olist"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS marketing"))
        conn.commit()

    results: dict[str, int] = {}
    for stem, (schema, table) in TABLE_MAP.items():
        csv_path = data_dir / f"{stem}.csv"
        if not csv_path.exists():
            print(f"  ⚠️  Missing: {csv_path} – skipping")
            continue

        t0 = time.monotonic()
        df = pd.read_csv(csv_path, low_memory=False)
        n_rows = len(df)
        df.to_sql(
            name=table,
            schema=schema,
            con=engine,
            if_exists="replace",
            index=False,
            chunksize=10_000,
            method="multi",
        )
        elapsed = time.monotonic() - t0
        fqn = f"{schema}.{table}"
        results[fqn] = n_rows
        print(f"  ✅  {fqn}: {n_rows:,} rows ({elapsed:.1f}s)")

    engine.dispose()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed PostgreSQL with Olist data")
    parser.add_argument("--data-dir", default=str(RAW_DATA_DIR))
    args = parser.parse_args()

    print(f"Seeding PostgreSQL at {POSTGRES_URL} …")
    results = seed(Path(args.data_dir))
    total = sum(results.values())
    print(f"\n✅  Done. {len(results)} tables, {total:,} rows total.")


if __name__ == "__main__":
    main()
