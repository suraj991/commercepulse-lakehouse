"""Export the current Iceberg silver snapshot to Parquet for dbt consumption.

Decision (documented in docs/decisions.md):
  Why export to Parquet instead of dbt reading Iceberg directly?
  - DuckDB (local dbt target) cannot read Iceberg REST/Hadoop catalogs.
  - Parquet export gives dbt a stable, versioned input file per run.
  - The manifest records snapshot IDs and checksums for lineage tracing.

Exports to: data/gold_input/<table>/snapshot_<id>/data.parquet
Manifest:   data/gold_input/manifest.json

Usage:
    python -m lakehouse.export_snapshot
    python -m lakehouse.export_snapshot --table orders --table sellers
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPORT_DIR = Path("data/gold_input")
MANIFEST_PATH = EXPORT_DIR / "manifest.json"

SILVER_TABLES = [
    "orders",
    "order_items",
    "order_payments",
    "order_reviews",
    "customers",
    "sellers",
    "products",
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export_table(spark: Any, table_name: str) -> dict[str, Any]:
    """Export one silver Iceberg table to Parquet. Returns export metadata."""
    t0 = time.monotonic()
    full_name = f"local.silver.{table_name}"

    # Get current snapshot ID
    history = spark.sql(
        f"SELECT snapshot_id, made_current_at FROM {full_name}.history ORDER BY made_current_at DESC LIMIT 1"
    ).collect()

    if not history:
        return {"table": table_name, "status": "no_snapshot"}

    snapshot_id = history[0]["snapshot_id"]
    made_current_at = str(history[0]["made_current_at"])

    # Export path
    out_dir = EXPORT_DIR / table_name / f"snapshot_{snapshot_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / "data.parquet"

    df = spark.table(full_name)
    row_count = df.count()

    # Write as a single Parquet file (coalesce for determinism)
    df.coalesce(1).write.mode("overwrite").parquet(str(parquet_path.parent / "_tmp"))
    # Find the part file Spark wrote
    tmp_dir = parquet_path.parent / "_tmp"
    part_files = list(tmp_dir.glob("part-*.parquet"))
    if part_files:
        import shutil
        shutil.copy2(str(part_files[0]), str(parquet_path))
        shutil.rmtree(str(tmp_dir))

    checksum = _sha256_file(parquet_path) if parquet_path.exists() else None
    elapsed = time.monotonic() - t0

    return {
        "table": table_name,
        "status": "ok",
        "snapshot_id": snapshot_id,
        "made_current_at": made_current_at,
        "row_count": row_count,
        "parquet_path": str(parquet_path),
        "sha256": checksum,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(elapsed, 1),
    }


def export(tables: list[str] | None = None) -> dict[str, Any]:
    """Export silver tables to Parquet and write manifest."""
    from lakehouse.spark_session import get_spark

    if tables is None:
        tables = SILVER_TABLES

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    spark = get_spark(app_name="CommercePulse-Export")

    results: dict[str, Any] = {}
    for tbl in tables:
        print(f"  Exporting {tbl} …")
        result = export_table(spark, tbl)
        results[tbl] = result
        if result["status"] == "ok":
            print(
                f"  ✅  {tbl}: {result['row_count']:,} rows "
                f"→ {result['parquet_path']} ({result['elapsed_s']}s)"
            )
        else:
            print(f"  ⚠️  {tbl}: {result['status']}")

    manifest = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tables": results,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, default=str))
    print(f"\n✅  Manifest written to {MANIFEST_PATH}")

    spark.stop()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Iceberg silver snapshots to Parquet")
    parser.add_argument("--table", nargs="*", help="Tables to export (default: all)")
    args = parser.parse_args()

    print("Exporting silver snapshots to Parquet …")
    export(tables=args.table)


if __name__ == "__main__":
    main()
