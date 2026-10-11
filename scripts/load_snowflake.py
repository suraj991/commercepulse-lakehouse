"""Load Parquet + FX JSON data into Snowflake raw schema.

Usage:
    python3 load_snowflake.py

Loads tables: orders, order_items, order_payments, order_reviews,
              customers, sellers, products,
              product_category_translations, mql, closed_deals,
              fx_rates (from JSON cache)

Strategy:
  1. PUT parquet/json file to internal stage @~/<table>/<file>
  2. COPY INTO raw.<table> FROM the stage
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, load_pem_private_key
)
from dotenv import load_dotenv
import snowflake.connector

PROJECT_ROOT = Path("/Users/suraj/Documents/Personal Projects/CommercePulse - Reliable E-commerce Lakehouse")
GOLD_INPUT = PROJECT_ROOT / "data" / "gold_input"
FX_CACHE = PROJECT_ROOT / "data" / "fx_cache"


def get_conn():
    load_dotenv(PROJECT_ROOT / ".env")
    with open(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"], "rb") as f:
        pk = load_pem_private_key(f.read(), password=None)
    pk_bytes = pk.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=pk_bytes,
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
    )


# Schema definitions for each table
TABLE_SCHEMAS = {
    "orders": """(
        order_id VARCHAR,
        customer_id VARCHAR,
        order_status VARCHAR,
        order_purchase_timestamp TIMESTAMP_NTZ,
        order_approved_at TIMESTAMP_NTZ,
        order_delivered_carrier_date TIMESTAMP_NTZ,
        order_delivered_customer_date TIMESTAMP_NTZ,
        order_estimated_delivery_date TIMESTAMP_NTZ
    )""",
    "order_items": """(
        order_id VARCHAR,
        order_item_id NUMBER,
        product_id VARCHAR,
        seller_id VARCHAR,
        shipping_limit_date TIMESTAMP_NTZ,
        price FLOAT,
        freight_value FLOAT
    )""",
    "order_payments": """(
        order_id VARCHAR,
        payment_sequential NUMBER,
        payment_type VARCHAR,
        payment_installments NUMBER,
        payment_value FLOAT
    )""",
    "order_reviews": """(
        review_id VARCHAR,
        order_id VARCHAR,
        review_score NUMBER,
        review_comment_title VARCHAR,
        review_comment_message VARCHAR,
        review_creation_date TIMESTAMP_NTZ,
        review_answer_timestamp TIMESTAMP_NTZ
    )""",
    "customers": """(
        customer_id VARCHAR,
        customer_unique_id VARCHAR,
        customer_zip_code_prefix VARCHAR,
        customer_city VARCHAR,
        customer_state VARCHAR
    )""",
    "sellers": """(
        seller_id VARCHAR,
        seller_zip_code_prefix VARCHAR,
        seller_city VARCHAR,
        seller_state VARCHAR,
        _ingested_at TIMESTAMP_NTZ
    )""",
    "products": """(
        product_id VARCHAR,
        product_category_name VARCHAR,
        product_name_lenght NUMBER,
        product_description_lenght NUMBER,
        product_photos_qty NUMBER,
        product_weight_g FLOAT,
        product_length_cm FLOAT,
        product_height_cm FLOAT,
        product_width_cm FLOAT
    )""",
    "product_category_translations": """(
        product_category_name VARCHAR,
        product_category_name_english VARCHAR
    )""",
    "mql": """(
        mql_id VARCHAR,
        first_contact_date DATE,
        landing_page_id VARCHAR,
        origin VARCHAR
    )""",
    "closed_deals": """(
        mql_id VARCHAR,
        seller_id VARCHAR,
        sdr_id VARCHAR,
        sr_id VARCHAR,
        won_date TIMESTAMP_NTZ,
        business_segment VARCHAR,
        lead_type VARCHAR,
        lead_behaviour_profile VARCHAR,
        has_company VARCHAR,
        has_gtin VARCHAR,
        average_stock VARCHAR,
        business_type VARCHAR,
        declared_product_catalog_size FLOAT,
        declared_monthly_revenue FLOAT
    )""",
    "fx_rates": """(
        rate_date DATE,
        base VARCHAR,
        brl_to_usd FLOAT
    )""",
}


def setup_schema(cur):
    """Create raw schema and stage."""
    print("Setting up raw schema and stage...")
    cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
    cur.execute("CREATE STAGE IF NOT EXISTS raw.parquet_stage FILE_FORMAT = (TYPE = PARQUET)")
    cur.execute("CREATE STAGE IF NOT EXISTS raw.json_stage FILE_FORMAT = (TYPE = JSON)")
    print("  Schema and stages created.")


def drop_and_create_table(cur, table_name):
    schema = TABLE_SCHEMAS[table_name]
    cur.execute(f"DROP TABLE IF EXISTS raw.{table_name}")
    cur.execute(f"CREATE TABLE raw.{table_name} {schema}")
    print(f"  Created raw.{table_name}")


def load_parquet_table(conn, cur, table_name):
    """PUT parquet file to stage and COPY INTO table."""
    pattern = str(GOLD_INPUT / table_name / "*/data.parquet")
    files = glob.glob(pattern)
    if not files:
        print(f"  WARNING: no parquet found for {table_name} at {pattern}")
        return 0

    parquet_path = files[0]
    print(f"  Loading {table_name} from {parquet_path}")

    stage_path = f"@raw.parquet_stage/{table_name}/"

    # PUT the file
    put_result = cur.execute(
        f"PUT 'file://{parquet_path}' '{stage_path}' AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
    ).fetchall()
    print(f"    PUT result: {put_result[0][6] if put_result else 'unknown'}")

    # COPY INTO using MATCH_BY_COLUMN_NAME (Parquet preserves column names)
    copy_sql = f"""
    COPY INTO raw.{table_name}
    FROM {stage_path}
    FILE_FORMAT = (TYPE = PARQUET)
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
    PURGE = FALSE
    ON_ERROR = ABORT_STATEMENT
    """
    copy_result = cur.execute(copy_sql).fetchall()
    rows_loaded = sum(r[3] for r in copy_result) if copy_result else 0
    print(f"    COPY result: {rows_loaded} rows loaded")
    return rows_loaded


def load_fx_rates(conn, cur):
    """Read FX JSON files and INSERT directly into raw.fx_rates."""
    print("  Loading fx_rates from JSON cache...")
    fx_files = sorted(glob.glob(str(FX_CACHE / "*.json")))
    if not fx_files:
        print("  WARNING: no FX JSON files found")
        return 0

    rows = []
    for fpath in fx_files:
        try:
            with open(fpath) as f:
                data = json.load(f)
            rate_date = data.get("date")
            base = data.get("base", "BRL")
            usd_rate = data.get("rates", {}).get("USD")
            if rate_date and usd_rate is not None:
                rows.append((rate_date, base, float(usd_rate)))
        except Exception as e:
            print(f"    Skip {fpath}: {e}")

    # Deduplicate (weekend files share date with trading day)
    seen_dates = {}
    for rate_date, base, usd_rate in rows:
        if rate_date not in seen_dates:
            seen_dates[rate_date] = (base, usd_rate)

    unique_rows = [(d, b, u) for d, (b, u) in seen_dates.items()]
    print(f"    {len(unique_rows)} unique trading days to insert")

    # Batch insert in chunks
    chunk_size = 500
    total_inserted = 0
    for i in range(0, len(unique_rows), chunk_size):
        chunk = unique_rows[i:i + chunk_size]
        values_str = ", ".join(f"('{r[0]}', '{r[1]}', {r[2]})" for r in chunk)
        cur.execute(f"INSERT INTO raw.fx_rates (rate_date, base, brl_to_usd) VALUES {values_str}")
        total_inserted += len(chunk)

    print(f"    {total_inserted} rows inserted into raw.fx_rates")
    return total_inserted


def main():
    conn = get_conn()
    cur = conn.cursor()

    print("=== Snowflake Raw Schema Loader ===\n")

    # Setup
    cur.execute("USE DATABASE commercepulse")
    setup_schema(cur)

    row_counts = {}

    # Load parquet tables
    parquet_tables = [
        "orders", "order_items", "order_payments", "order_reviews",
        "customers", "sellers", "products",
        "product_category_translations", "mql", "closed_deals"
    ]

    for table_name in parquet_tables:
        print(f"\nLoading {table_name}...")
        drop_and_create_table(cur, table_name)
        count = load_parquet_table(conn, cur, table_name)
        row_counts[table_name] = count

    # Load FX rates
    print("\nLoading fx_rates...")
    drop_and_create_table(cur, "fx_rates")
    count = load_fx_rates(conn, cur)
    row_counts["fx_rates"] = count

    # Verify
    print("\n=== Row Counts Verification ===")
    for table_name in parquet_tables + ["fx_rates"]:
        cur.execute(f"SELECT COUNT(*) FROM raw.{table_name}")
        actual = cur.fetchone()[0]
        print(f"  raw.{table_name}: {actual:,} rows")
        row_counts[table_name] = actual

    conn.close()
    print("\nDone. All tables loaded.")
    return row_counts


if __name__ == "__main__":
    main()
