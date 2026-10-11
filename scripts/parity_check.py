"""Phase 8 parity check: compare DuckDB (ground truth) vs Snowflake.

Queries the same metrics from both databases and reports PASS/FAIL.
Exit code 0 = all PASS, 1 = at least one FAIL.

Usage:
    python3 scripts/parity_check.py
    # With .env loaded (load_dotenv picks it up automatically)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# --- DuckDB queries ---
import duckdb

# --- Snowflake ---
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, load_pem_private_key
)
from dotenv import load_dotenv
import snowflake.connector

load_dotenv(PROJECT_ROOT / ".env")

TOLERANCE = 0.01  # BRL tolerance for GMV values


# ── Metric definitions ─────────────────────────────────────────────────────────

METRICS = [
    {
        "name": "fct_orders row count",
        "duck_sql": "SELECT COUNT(*) FROM fct_orders",
        "snow_sql": "SELECT COUNT(*) FROM analytics.fct_orders",
        "exact": True,
    },
    {
        "name": "fct_order_items row count",
        "duck_sql": "SELECT COUNT(*) FROM fct_order_items",
        "snow_sql": "SELECT COUNT(*) FROM analytics.fct_order_items",
        "exact": True,
    },
    {
        "name": "fct_payments row count",
        "duck_sql": "SELECT COUNT(*) FROM fct_payments",
        "snow_sql": "SELECT COUNT(*) FROM analytics.fct_payments",
        "exact": True,
    },
    {
        "name": "fct_seller_leads row count",
        "duck_sql": "SELECT COUNT(*) FROM fct_seller_leads",
        "snow_sql": "SELECT COUNT(*) FROM analytics.fct_seller_leads",
        "exact": True,
    },
    {
        "name": "fulfilled_gmv (is_delivered=1)",
        "duck_sql": "SELECT ROUND(SUM(gmv_brl), 2) FROM fct_orders WHERE is_delivered = 1",
        "snow_sql": "SELECT ROUND(SUM(gmv_brl), 2) FROM analytics.fct_orders WHERE is_delivered = 1",
        "exact": False,
    },
    {
        "name": "total_gmv (all orders)",
        "duck_sql": "SELECT ROUND(SUM(gmv_brl), 2) FROM fct_orders",
        "snow_sql": "SELECT ROUND(SUM(gmv_brl), 2) FROM analytics.fct_orders",
        "exact": False,
    },
]


# ── Connect ────────────────────────────────────────────────────────────────────

def get_duck():
    return duckdb.connect(str(PROJECT_ROOT / "data" / "commercepulse.duckdb"))


def get_snow():
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


# ── Run checks ─────────────────────────────────────────────────────────────────

def run():
    duck = get_duck()
    snow = get_snow()
    snow_cur = snow.cursor()

    results = []
    all_pass = True

    print("\n" + "=" * 70)
    print("CommercePulse Phase 8 – DuckDB vs Snowflake Parity Check")
    print("=" * 70)
    print(f"{'Metric':<40} {'DuckDB':>16} {'Snowflake':>16} {'Status':>8}")
    print("-" * 84)

    for m in METRICS:
        duck_val = duck.execute(m["duck_sql"]).fetchone()[0]
        snow_cur.execute(m["snow_sql"])
        snow_val = snow_cur.fetchone()[0]

        if m["exact"]:
            passed = duck_val == snow_val
        else:
            # Floating-point tolerance
            try:
                passed = abs(float(duck_val) - float(snow_val)) <= TOLERANCE
            except (TypeError, ValueError):
                passed = duck_val == snow_val

        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False

        results.append({
            "metric": m["name"],
            "duckdb": duck_val,
            "snowflake": snow_val,
            "status": status,
        })

        duck_str = f"{duck_val:,.2f}" if isinstance(duck_val, float) else f"{duck_val:,}"
        snow_str = f"{snow_val:,.2f}" if isinstance(snow_val, float) else f"{snow_val:,}"
        print(f"{m['name']:<40} {duck_str:>16} {snow_str:>16} {status:>8}")

    print("=" * 84)
    overall = "ALL PASS" if all_pass else "FAILURES DETECTED"
    print(f"Overall: {overall}")

    duck.close()
    snow_cur.close()
    snow.close()

    return all_pass, results


if __name__ == "__main__":
    ok, results = run()
    sys.exit(0 if ok else 1)
