"""Bronze extractor: reads bounded date intervals from Postgres → Parquet on MinIO.

Design:
- Extracts are idempotent within a run_id.
- A capture ledger tracks: run_id, table, bounds, row_count, file_hash, schema_version.
- Running the same extract twice creates no duplicate data (ledger deduplication).
- Writes immutable Parquet objects; never overwrites existing objects.

Usage:
    python -m ingestion.extractor
    python -m ingestion.extractor --table orders --start 2017-01-01 --end 2017-12-31
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from minio import Minio
from minio.error import S3Error
from sqlalchemy import create_engine, text

from ingestion.config import (
    MINIO_BRONZE_BUCKET,
    POSTGRES_URL,
    get_minio_client,
)

# ── Table extraction config ───────────────────────────────────────────────────
# Each entry: (schema, table, date_column_for_partitioning)
EXTRACT_TABLES: dict[str, tuple[str, str, str | None]] = {
    "orders": ("olist", "orders", "order_purchase_timestamp"),
    "order_items": ("olist", "order_items", "shipping_limit_date"),
    "order_payments": ("olist", "order_payments", None),
    "order_reviews": ("olist", "order_reviews", "review_creation_date"),
    "customers": ("olist", "customers", None),
    "sellers": ("olist", "sellers", None),
    "products": ("olist", "products", None),
    "geolocation": ("olist", "geolocation", None),
    "product_category_translations": ("olist", "product_category_translations", None),
    "mql": ("marketing", "mql", "first_contact_date"),
    "closed_deals": ("marketing", "closed_deals", "won_date"),
}

LEDGER_BUCKET = MINIO_BRONZE_BUCKET
LEDGER_PREFIX = "_ledger/"


def _ensure_bucket(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def _load_ledger(client: Minio) -> list[dict[str, Any]]:
    """Load all ledger entries from MinIO."""
    entries: list[dict[str, Any]] = []
    try:
        objects = client.list_objects(LEDGER_BUCKET, prefix=LEDGER_PREFIX)
        for obj in objects:
            resp = client.get_object(LEDGER_BUCKET, obj.object_name)
            entries.append(json.loads(resp.read().decode()))
    except S3Error:
        pass
    return entries


def _save_ledger_entry(client: Minio, entry: dict[str, Any]) -> None:
    """Append a ledger entry as a JSON object to MinIO."""
    key = f"{LEDGER_PREFIX}{entry['run_id']}_{entry['table']}.json"
    data = json.dumps(entry, indent=2, default=str).encode()
    client.put_object(
        LEDGER_BUCKET,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type="application/json",
    )


def _ledger_entry_exists(ledger: list[dict], run_id: str, table: str) -> bool:
    return any(e["run_id"] == run_id and e["table"] == table for e in ledger)


def _extract_table(
    engine: Any,
    schema: str,
    table: str,
    date_col: str | None,
    start_date: date | None,
    end_date: date | None,
) -> pd.DataFrame:
    """Read a table (with optional date-bounded WHERE clause) from Postgres."""
    fqn = f'"{schema}"."{table}"'
    if date_col and start_date and end_date:
        query = text(
            f"SELECT * FROM {fqn} "
            f"WHERE {date_col} >= :start AND {date_col} < :end"
        )
        return pd.read_sql(query, engine, params={"start": start_date, "end": end_date})
    return pd.read_sql(text(f"SELECT * FROM {fqn}"), engine)


def _write_parquet_to_minio(
    client: Minio,
    df: pd.DataFrame,
    object_key: str,
    bucket: str = MINIO_BRONZE_BUCKET,
) -> tuple[int, str]:
    """Write DataFrame as Parquet to MinIO. Returns (byte_count, sha256)."""
    arrow_table = pa.Table.from_pandas(df, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(arrow_table, buf, compression="snappy")
    buf.seek(0)
    data = buf.read()
    file_hash = hashlib.sha256(data).hexdigest()
    client.put_object(
        bucket,
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type="application/octet-stream",
    )
    return len(data), file_hash


def extract(
    tables: list[str] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run bronze extraction. Returns a summary dict.

    Args:
        tables: list of logical table names to extract (default: all)
        start_date: lower bound for date-partitioned tables
        end_date: upper bound (exclusive) for date-partitioned tables
        run_id: explicit run ID (auto-generated if None)
    """
    if run_id is None:
        run_id = str(uuid.uuid4())[:8]
    if tables is None:
        tables = list(EXTRACT_TABLES.keys())

    ts_start = datetime.now(timezone.utc)
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    client = get_minio_client()
    _ensure_bucket(client, MINIO_BRONZE_BUCKET)
    ledger = _load_ledger(client)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "started_at": ts_start.isoformat(),
        "results": {},
    }

    for tbl_name in tables:
        if tbl_name not in EXTRACT_TABLES:
            print(f"  ⚠️  Unknown table '{tbl_name}' – skipping")
            continue

        schema, table, date_col = EXTRACT_TABLES[tbl_name]

        if _ledger_entry_exists(ledger, run_id, tbl_name):
            print(f"  ⏭️   {tbl_name}: already in ledger for run_id={run_id}, skipping")
            continue

        t0 = time.monotonic()
        df = _extract_table(engine, schema, table, date_col, start_date, end_date)
        n_rows = len(df)

        bounds_str = ""
        if start_date and end_date:
            bounds_str = f"_{start_date.isoformat()}_{end_date.isoformat()}"
        object_key = f"bronze/{tbl_name}/{run_id}{bounds_str}/data.parquet"

        file_bytes, file_hash = _write_parquet_to_minio(client, df, object_key)
        elapsed = time.monotonic() - t0

        # Infer schema version from column list
        schema_version = hashlib.md5(
            ",".join(sorted(df.columns)).encode()
        ).hexdigest()[:8]

        ledger_entry: dict[str, Any] = {
            "run_id": run_id,
            "table": tbl_name,
            "schema": schema,
            "source_table": f"{schema}.{table}",
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "row_count": n_rows,
            "file_bytes": file_bytes,
            "file_hash": file_hash,
            "object_key": object_key,
            "schema_version": schema_version,
            "columns": list(df.columns),
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": round(elapsed, 2),
        }
        _save_ledger_entry(client, ledger_entry)
        ledger.append(ledger_entry)

        summary["results"][tbl_name] = ledger_entry
        print(
            f"  ✅  {tbl_name}: {n_rows:,} rows → {object_key} "
            f"({file_bytes / 1024:.0f} KB, {elapsed:.1f}s)"
        )

    engine.dispose()
    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    summary["total_rows"] = sum(r.get("row_count", 0) for r in summary["results"].values())
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Bronze extractor: Postgres → MinIO Parquet")
    parser.add_argument("--table", nargs="*", help="Tables to extract (default: all)")
    parser.add_argument("--start", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", help="End date YYYY-MM-DD (exclusive)")
    parser.add_argument("--run-id", help="Explicit run ID (auto-generated if omitted)")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start) if args.start else None
    end_date = date.fromisoformat(args.end) if args.end else None

    print(f"Starting bronze extraction run …")
    summary = extract(
        tables=args.table,
        start_date=start_date,
        end_date=end_date,
        run_id=args.run_id,
    )
    print(
        f"\n✅  run_id={summary['run_id']}: "
        f"{len(summary['results'])} tables, {summary['total_rows']:,} rows"
    )


if __name__ == "__main__":
    main()
