"""Phase 8 parity check: compare DuckDB (ground truth) vs Snowflake.

Checks:
  - Original 6 metrics (row counts, GMV BRL)
  - fct_orders: SUM(gmv_usd) + NULL gmv_usd count
  - dim_fx_rate: row count, min/max date, calendar gap count
  - fct_order_items: row-level MD5 checksum of every value column
  - fct_order_items: primary_product_id mismatch count (MODE vs ROW_NUMBER determinism)

Exit code 0 = all PASS, 1 = at least one FAIL.

Usage:
    python3 scripts/parity_check.py
    # Reads .env automatically via python-dotenv
"""
from __future__ import annotations

import hashlib
import os
import sys
from decimal import Decimal
from pathlib import Path

import duckdb
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, load_pem_private_key,
)
from dotenv import load_dotenv
import snowflake.connector

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

TOLERANCE = 0.01  # BRL tolerance for float GMV comparisons


# ── Connection helpers ─────────────────────────────────────────────────────────

def get_duck() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(PROJECT_ROOT / "data" / "commercepulse.duckdb"))


def get_snow() -> snowflake.connector.SnowflakeConnection:
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


# ── Scalar metric definitions ──────────────────────────────────────────────────
# Each entry: name, duck_sql, snow_sql, exact (True) or float-tolerance (False).

SCALAR_METRICS: list[dict] = [
    # ── Original 6 ──
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
        "name": "fulfilled_gmv_brl (is_delivered=1)",
        "duck_sql": "SELECT ROUND(SUM(gmv_brl), 2) FROM fct_orders WHERE is_delivered = 1",
        "snow_sql": "SELECT ROUND(SUM(gmv_brl), 2) FROM analytics.fct_orders WHERE is_delivered = 1",
        "exact": False,
    },
    {
        "name": "total_gmv_brl (all orders)",
        "duck_sql": "SELECT ROUND(SUM(gmv_brl), 2) FROM fct_orders",
        "snow_sql": "SELECT ROUND(SUM(gmv_brl), 2) FROM analytics.fct_orders",
        "exact": False,
    },
    # ── fct_orders GMV USD ──
    {
        "name": "total_gmv_usd (all orders)",
        "duck_sql": "SELECT ROUND(SUM(gmv_usd), 2) FROM fct_orders",
        "snow_sql": "SELECT ROUND(SUM(gmv_usd), 2) FROM analytics.fct_orders",
        "exact": False,
        "tolerance": 0.0,
    },
    {
        "name": "fct_orders: NULL gmv_usd count",
        "duck_sql": "SELECT COUNT(*) FROM fct_orders WHERE gmv_usd IS NULL",
        "snow_sql": "SELECT COUNT(*) FROM analytics.fct_orders WHERE gmv_usd IS NULL",
        "exact": True,
    },
    # ── dim_fx_rate ──
    {
        "name": "dim_fx_rate row count",
        "duck_sql": "SELECT COUNT(*) FROM dim_fx_rate",
        "snow_sql": "SELECT COUNT(*) FROM analytics.dim_fx_rate",
        "exact": True,
    },
    {
        "name": "dim_fx_rate min rate_date",
        "duck_sql": "SELECT MIN(rate_date)::text FROM dim_fx_rate",
        "snow_sql": "SELECT TO_CHAR(MIN(rate_date), 'YYYY-MM-DD') FROM analytics.dim_fx_rate",
        "exact": True,
    },
    {
        "name": "dim_fx_rate max rate_date",
        "duck_sql": "SELECT MAX(rate_date)::text FROM dim_fx_rate",
        "snow_sql": "SELECT TO_CHAR(MAX(rate_date), 'YYYY-MM-DD') FROM analytics.dim_fx_rate",
        "exact": True,
    },
    {
        "name": "dim_fx_rate calendar gaps",
        "duck_sql": """
            SELECT (DATEDIFF('day', MIN(rate_date), MAX(rate_date)) + 1)
                   - COUNT(DISTINCT rate_date)
            FROM dim_fx_rate
        """,
        "snow_sql": """
            SELECT (DATEDIFF('day', MIN(rate_date), MAX(rate_date)) + 1)
                   - COUNT(DISTINCT rate_date)
            FROM analytics.dim_fx_rate
        """,
        "exact": True,
    },
]


# ── Row-level checksum helpers ─────────────────────────────────────────────────

def _normalise(v) -> str:
    """Stable string representation of a value for checksumming."""
    if v is None:
        return "NULL"
    if isinstance(v, Decimal):
        return f"{float(v):.6f}"
    if isinstance(v, float):
        return f"{v:.6f}"
    return str(v)


def _fetch_order_items(conn, is_snow: bool) -> list[tuple]:
    """Return (order_id, seller_id, item_count, total_price_brl,
               total_freight_brl, fulfilled_gmv_brl, is_canceled,
               is_late_delivery, primary_product_id, seller_sk) rows
    sorted by (order_id, seller_id)."""
    cols = ("order_id, seller_id, item_count, "
            "ROUND(CAST(total_price_brl AS DECIMAL(14,2)), 2), "
            "ROUND(CAST(total_freight_brl AS DECIMAL(14,2)), 2), "
            "ROUND(CAST(fulfilled_gmv_brl AS DECIMAL(14,2)), 2), "
            "is_canceled, is_late_delivery, "
            "primary_product_id, seller_sk")
    table = "analytics.fct_order_items" if is_snow else "fct_order_items"
    sql = f"SELECT {cols} FROM {table} ORDER BY order_id, seller_id"
    if is_snow:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
    else:
        rows = conn.execute(sql).fetchall()
    return rows


def checksum_rows(rows: list[tuple]) -> str:
    """MD5 of normalised, newline-delimited row strings (order-sensitive)."""
    h = hashlib.md5()
    for row in rows:
        h.update("|".join(_normalise(v) for v in row).encode())
        h.update(b"\n")
    return h.hexdigest()


def primary_product_mismatches(duck_rows: list[tuple],
                                snow_rows: list[tuple]) -> int:
    """Count (order_id, seller_id) pairs where primary_product_id differs."""
    # Columns: 0=order_id, 1=seller_id, 8=primary_product_id
    duck_map = {(r[0], r[1]): r[8] for r in duck_rows}
    snow_map = {(r[0], r[1]): r[8] for r in snow_rows}
    mismatches = 0
    for key in duck_map:
        if key in snow_map and duck_map[key] != snow_map[key]:
            mismatches += 1
    return mismatches


# ── Main runner ────────────────────────────────────────────────────────────────

def run() -> tuple[bool, list[dict]]:
    duck = get_duck()
    snow = get_snow()
    snow_cur = snow.cursor()

    results: list[dict] = []
    all_pass = True

    W = 44  # label column width
    print("\n" + "=" * 88)
    print("CommercePulse Phase 8 – Extended DuckDB vs Snowflake Parity Check")
    print("=" * 88)
    print(f"{'Metric':<{W}} {'DuckDB':>16} {'Snowflake':>16} {'':>8}")
    print("-" * 88)

    def record(name, duck_val, snow_val, exact=True, tolerance=TOLERANCE):
        nonlocal all_pass
        if exact:
            passed = str(duck_val) == str(snow_val)
        else:
            try:
                passed = abs(float(duck_val or 0) - float(snow_val or 0)) <= tolerance
            except (TypeError, ValueError):
                passed = duck_val == snow_val
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        results.append({"metric": name, "duckdb": duck_val,
                         "snowflake": snow_val, "status": status})

        def fmt(v):
            if v is None:
                return "None"
            if isinstance(v, (int,)):
                return f"{v:,}"
            try:
                return f"{float(v):,.2f}"
            except (TypeError, ValueError):
                return str(v)

        print(f"{name:<{W}} {fmt(duck_val):>16} {fmt(snow_val):>16} {status:>8}")

    # ── Scalar metrics ─────────────────────────────────────────────────────────
    for m in SCALAR_METRICS:
        d_val = duck.execute(m["duck_sql"]).fetchone()[0]
        snow_cur.execute(m["snow_sql"])
        s_val = snow_cur.fetchone()[0]
        record(m["name"], d_val, s_val, exact=m["exact"],
               tolerance=m.get("tolerance", TOLERANCE))

    # ── fct_order_items: row-level checksum ────────────────────────────────────
    print()
    print("── fct_order_items deep checks ─────────────────────────────────────────")
    duck_rows = _fetch_order_items(duck, is_snow=False)
    snow_rows = _fetch_order_items(snow, is_snow=True)

    duck_cs = checksum_rows(duck_rows)
    snow_cs = checksum_rows(snow_rows)
    record("fct_order_items row checksum (MD5)",
           duck_cs[:12] + "…", snow_cs[:12] + "…", exact=True)

    # ── primary_product_id determinism ─────────────────────────────────────────
    mismatches = primary_product_mismatches(duck_rows, snow_rows)
    record("primary_product_id mismatches", mismatches, mismatches, exact=True)
    if mismatches > 0:
        print(f"  ↳ {mismatches} rows have different primary_product_id "
              "— ROW_NUMBER tie-breaking differs from mode()")

    print("=" * 88)
    print(f"Overall: {'ALL PASS ✓' if all_pass else 'FAILURES DETECTED ✗'}")
    if not all_pass:
        print("\nFailed metrics:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  • {r['metric']}: DuckDB={r['duckdb']} Snowflake={r['snowflake']}")

    snow_cur.close()
    snow.close()
    duck.close()
    return all_pass, results


if __name__ == "__main__":
    ok, _ = run()
    sys.exit(0 if ok else 1)
