"""Write a publication record after a successful quality gate.

Each run produces:
    data/publications/{publication_id}.json

with a snapshot of key metrics and a stable publication_id for lineage tracing.

Usage:
    python scripts/publish.py --run-id <airflow_run_id> --dag-run-date 2026-10-10
    python scripts/publish.py   # for manual / local runs
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def collect_metrics(db_path: Path) -> dict:
    """Query DuckDB for publication metrics snapshot."""
    import duckdb

    conn = duckdb.connect(str(db_path), read_only=True)
    row = conn.execute("""
        select
            count(*)                                        as order_count,
            count(*) filter (where is_delivered = 1)        as delivered_count,
            sum(gmv_brl)                                    as total_gmv_brl,
            sum(gmv_brl) filter (where is_delivered = 1)    as fulfilled_gmv_brl,
            count(distinct customer_state)                  as distinct_states
        from fct_orders
    """).fetchone()
    conn.close()

    if row:
        return {
            "order_count":       row[0],
            "delivered_count":   row[1],
            "total_gmv_brl":     round(row[2] or 0, 2),
            "fulfilled_gmv_brl": round(row[3] or 0, 2),
            "distinct_states":   row[4],
        }
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Write CommercePulse publication record")
    parser.add_argument("--run-id",       default="", help="Airflow run_id (optional)")
    parser.add_argument("--dag-run-date", default="", help="DAG run date YYYY-MM-DD (optional)")
    parser.add_argument(
        "--db",
        default="data/commercepulse.duckdb",
        help="DuckDB path (default: data/commercepulse.duckdb)",
    )
    parser.add_argument(
        "--out-dir",
        default="data/publications",
        help="Output directory for publication JSON",
    )
    args = parser.parse_args()

    db_path  = Path(args.db)
    out_dir  = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    publication_id = str(uuid.uuid4())
    metrics = collect_metrics(db_path) if db_path.exists() else {}

    record = {
        "publication_id":   publication_id,
        "airflow_run_id":   args.run_id or "manual",
        "dag_run_date":     args.dag_run_date or "",
        "published_at":     datetime.now(timezone.utc).isoformat(),
        "quality_gate":     "passed",
        "metrics":          metrics,
        "dbt_db":           str(db_path),
    }

    out_path = out_dir / f"{publication_id}.json"
    out_path.write_text(json.dumps(record, indent=2, default=float))
    print(f"✅  Published: {out_path}")
    print(f"    publication_id: {publication_id}")
    if metrics:
        print(f"    orders: {metrics.get('order_count', 0):,}  "
              f"delivered: {metrics.get('delivered_count', 0):,}  "
              f"fulfilled_gmv_brl: {metrics.get('fulfilled_gmv_brl', 0):,.2f}")


if __name__ == "__main__":
    main()
