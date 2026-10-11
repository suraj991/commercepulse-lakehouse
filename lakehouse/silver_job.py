"""Silver layer PySpark job: bronze Parquet → validated, deduped Iceberg v2 tables.

Design:
- Reads latest Parquet file for each table from MinIO bronze bucket.
- Validates: null checks on PK/FK columns, enum checks on known categorical cols.
- Deduplicates using stable primary keys with deterministic version ordering.
- Invalid rows go to a reject table with a reason string.
- Writes Iceberg v2 tables in the local Hadoop catalog (data/iceberg_warehouse/).
- Lake checks: row counts, key uniqueness, reconciliation vs. bronze.
- Demonstrates: adding a new column (schema evolution) and snapshot queries.

Usage:
    python -m lakehouse.silver_job
    python -m lakehouse.silver_job --table orders
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType, TimestampType

from ingestion.config import MINIO_BRONZE_BUCKET, MINIO_ENDPOINT
from lakehouse.spark_session import get_spark

# ── Silver table definitions ───────────────────────────────────────────────────
# (table_name, bronze_prefix, pk_cols, dedup_order_col, nullable_checks)
SILVER_TABLES: dict[str, dict[str, Any]] = {
    "orders": {
        "bronze_prefix": "bronze/orders/",
        "pk": ["order_id"],
        "dedup_order": "order_purchase_timestamp",
        "not_null": ["order_id", "customer_id", "order_status", "order_purchase_timestamp"],
        "accepted_values": {
            "order_status": [
                "delivered", "shipped", "canceled", "unavailable",
                "invoiced", "processing", "created", "approved",
            ]
        },
    },
    "order_items": {
        "bronze_prefix": "bronze/order_items/",
        "pk": ["order_id", "order_item_id"],
        "dedup_order": "shipping_limit_date",
        "not_null": ["order_id", "order_item_id", "product_id", "seller_id", "price"],
        "accepted_values": {},
    },
    "order_payments": {
        "bronze_prefix": "bronze/order_payments/",
        "pk": ["order_id", "payment_sequential"],
        "dedup_order": None,
        "not_null": ["order_id", "payment_sequential", "payment_type", "payment_value"],
        "accepted_values": {},
    },
    "order_reviews": {
        "bronze_prefix": "bronze/order_reviews/",
        "pk": ["review_id", "order_id"],  # review_id alone not unique – see profiling
        "dedup_order": "review_answer_timestamp",
        "not_null": ["order_id", "review_score"],
        "accepted_values": {"review_score": ["1", "2", "3", "4", "5"]},
    },
    "customers": {
        "bronze_prefix": "bronze/customers/",
        "pk": ["customer_id"],
        "dedup_order": None,
        "not_null": ["customer_id", "customer_unique_id"],
        "accepted_values": {},
    },
    "sellers": {
        "bronze_prefix": "bronze/sellers/",
        "pk": ["seller_id"],
        "dedup_order": None,
        "not_null": ["seller_id"],
        "accepted_values": {},
    },
    "products": {
        "bronze_prefix": "bronze/products/",
        "pk": ["product_id"],
        "dedup_order": None,
        "not_null": ["product_id"],
        "accepted_values": {},
    },
}


def _find_latest_bronze(spark: SparkSession, prefix: str, bucket: str) -> str | None:
    """List objects with the given prefix and return the most recent path."""
    endpoint_no_scheme = MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
    from minio import Minio
    from ingestion.config import MINIO_ACCESS_KEY, MINIO_SECRET_KEY

    client = Minio(
        endpoint_no_scheme,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )
    objects = list(client.list_objects(bucket, prefix=prefix, recursive=True))
    parquets = [o for o in objects if o.object_name.endswith(".parquet")]
    if not parquets:
        return None
    # Sort by last_modified desc → newest file
    parquets.sort(key=lambda o: o.last_modified, reverse=True)
    return f"s3a://{bucket}/{parquets[0].object_name}"


def _validate_and_split(
    df: DataFrame,
    table_name: str,
    config: dict[str, Any],
) -> tuple[DataFrame, DataFrame]:
    """Split df into (valid, reject). Reject rows include a _reject_reason column."""
    reject_conditions: list[Any] = []

    # Null checks
    for col in config.get("not_null", []):
        if col in df.columns:
            reject_conditions.append(
                F.when(F.col(col).isNull(), F.lit(f"null:{col}"))
            )

    # Accepted-value checks (cast to string for comparison)
    for col, values in config.get("accepted_values", {}).items():
        if col in df.columns:
            reject_conditions.append(
                F.when(
                    ~F.col(col).cast(StringType()).isin(values),
                    F.lit(f"invalid_value:{col}"),
                )
            )

    if not reject_conditions:
        # No validation rules → all rows are valid
        valid = df
        schema = StructType([StructField("_reject_reason", StringType())])
        reject = spark.createDataFrame([], schema)  # type: ignore[name-defined]
        return valid, df.filter(F.lit(False))  # empty reject

    # Build reject reason: first non-null condition wins
    reason_expr = reject_conditions[0]
    for cond in reject_conditions[1:]:
        reason_expr = F.coalesce(reason_expr, cond)

    df_with_reason = df.withColumn("_reject_reason", reason_expr)
    reject = df_with_reason.filter(F.col("_reject_reason").isNotNull())
    valid = df_with_reason.filter(F.col("_reject_reason").isNull()).drop("_reject_reason")
    return valid, reject


def _dedup(df: DataFrame, pk: list[str], order_col: str | None) -> DataFrame:
    """Deduplicate df by pk, keeping the row with the greatest order_col value.

    If order_col is None, keeps an arbitrary row (all duplicates are equivalent).
    """
    from pyspark.sql.window import Window

    if order_col and order_col in df.columns:
        # PySpark 4.0 uses desc_nulls_last() function instead of .nullsLast() method
        w = Window.partitionBy(*pk).orderBy(F.desc_nulls_last(order_col))
    else:
        w = Window.partitionBy(*pk).orderBy(F.lit(1))

    return (
        df.withColumn("_row_num", F.row_number().over(w))
        .filter(F.col("_row_num") == 1)
        .drop("_row_num")
    )


def _write_iceberg(
    spark: SparkSession,
    df: DataFrame,
    table_name: str,
    schema_ns: str = "silver",
) -> None:
    """Write df to local.{schema_ns}.{table_name} as Iceberg v2 (overwrite)."""
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS local.{schema_ns}")
    full_name = f"local.{schema_ns}.{table_name}"
    df.writeTo(full_name).using("iceberg").tableProperty(
        "format-version", "2"
    ).createOrReplace()


def process_table(
    spark: SparkSession,
    table_name: str,
    config: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Process one bronze table through silver. Returns stats dict."""
    t0 = time.monotonic()
    bronze_path = _find_latest_bronze(spark, config["bronze_prefix"], MINIO_BRONZE_BUCKET)
    if bronze_path is None:
        return {"table": table_name, "status": "skipped", "reason": "no bronze file"}

    print(f"  Reading {bronze_path} …")
    df = spark.read.parquet(bronze_path)
    bronze_count = df.count()

    valid, reject = _validate_and_split(df, table_name, config)
    valid_count = valid.count()
    reject_count = reject.count()

    deduped = _dedup(valid, config["pk"], config.get("dedup_order"))
    deduped_count = deduped.count()

    if not dry_run:
        # Write silver table
        _write_iceberg(spark, deduped, table_name)
        # Write reject table if there are any rejects
        if reject_count > 0:
            _write_iceberg(spark, reject, f"{table_name}_rejects")

    elapsed = time.monotonic() - t0
    stats = {
        "table": table_name,
        "status": "ok",
        "bronze_count": bronze_count,
        "valid_count": valid_count,
        "reject_count": reject_count,
        "deduped_count": deduped_count,
        "dedup_removed": valid_count - deduped_count,
        "elapsed_s": round(elapsed, 1),
    }
    print(
        f"  ✅  {table_name}: bronze={bronze_count:,} "
        f"valid={valid_count:,} reject={reject_count:,} "
        f"deduped={deduped_count:,} ({elapsed:.1f}s)"
    )
    return stats


def lake_checks(spark: SparkSession, stats_list: list[dict[str, Any]]) -> list[str]:
    """Run post-write lake checks. Returns list of failure messages (empty = pass)."""
    failures: list[str] = []
    for stats in stats_list:
        if stats["status"] != "ok":
            continue
        tbl = stats["table"]
        full_name = f"local.silver.{tbl}"
        try:
            silver_count = spark.table(full_name).count()
        except Exception as e:
            failures.append(f"{tbl}: could not read silver table: {e}")
            continue

        expected = stats["deduped_count"]
        if silver_count != expected:
            failures.append(
                f"{tbl}: silver count {silver_count:,} != expected {expected:,}"
            )

        # Key uniqueness check
        config = SILVER_TABLES.get(tbl, {})
        pk = config.get("pk", [])
        if pk:
            df = spark.table(full_name)
            distinct_pk = df.select(*pk).distinct().count()
            total = df.count()
            if distinct_pk != total:
                failures.append(
                    f"{tbl}: PK not unique – {total - distinct_pk:,} duplicates"
                )

    return failures


def demo_schema_evolution(spark: SparkSession) -> None:
    """Demonstrate Iceberg schema evolution: add a column to silver.sellers.

    This shows:
    1. Current snapshot ID
    2. Add column _ingested_at
    3. New snapshot ID (different)
    4. Read old snapshot (no _ingested_at column)
    """
    tbl = "local.silver.sellers"
    try:
        # Before: note current snapshot
        history = spark.sql(f"SELECT snapshot_id, made_current_at FROM {tbl}.history").collect()
        snap_before = history[-1]["snapshot_id"] if history else None

        # Add column
        spark.sql(f"ALTER TABLE {tbl} ADD COLUMN _ingested_at TIMESTAMP")
        spark.sql(
            f"UPDATE {tbl} SET _ingested_at = CAST('{datetime.now(timezone.utc).isoformat()}' AS TIMESTAMP)"
        )

        # After: new snapshot
        history2 = spark.sql(f"SELECT snapshot_id, made_current_at FROM {tbl}.history").collect()
        snap_after = history2[-1]["snapshot_id"] if history2 else None

        print(f"\n  Schema evolution demo:")
        print(f"    Before snapshot: {snap_before}")
        print(f"    After snapshot:  {snap_after}")
        print(f"    Column added:    _ingested_at")
        print(f"    Snapshots differ: {snap_before != snap_after}")

        # Read old snapshot (time-travel)
        if snap_before:
            old_cols = spark.sql(
                f"SELECT * FROM {tbl} VERSION AS OF {snap_before} LIMIT 1"
            ).columns
            print(f"    Old snapshot columns: {old_cols}")
            has_new_col = "_ingested_at" in old_cols
            print(f"    Old snapshot has _ingested_at: {has_new_col} (expected False)")
    except Exception as e:
        print(f"  ⚠️  Schema evolution demo skipped: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Silver PySpark/Iceberg job")
    parser.add_argument("--table", nargs="*", help="Tables to process (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Validate only; don't write")
    args = parser.parse_args()

    tables = args.table or list(SILVER_TABLES.keys())

    print("Starting silver job …")
    spark = get_spark(app_name="CommercePulse-Silver")

    stats_list: list[dict[str, Any]] = []
    for tbl in tables:
        if tbl not in SILVER_TABLES:
            print(f"  ⚠️  Unknown table '{tbl}' – skipping")
            continue
        stats = process_table(spark, tbl, SILVER_TABLES[tbl], dry_run=args.dry_run)
        stats_list.append(stats)

    # Lake checks
    if not args.dry_run:
        failures = lake_checks(spark, stats_list)
        if failures:
            print(f"\n❌  Lake check failures ({len(failures)}):")
            for f in failures:
                print(f"    - {f}")
        else:
            total = sum(s.get("deduped_count", 0) for s in stats_list)
            print(f"\n✅  All lake checks passed. {total:,} rows across {len(stats_list)} tables.")

        # Demo schema evolution on sellers (small table)
        if "sellers" in tables:
            demo_schema_evolution(spark)

    spark.stop()


if __name__ == "__main__":
    main()
