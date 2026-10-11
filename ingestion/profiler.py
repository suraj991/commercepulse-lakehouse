"""Profile all Olist CSVs and write real numbers to docs/profiling.md.

Usage:
    python -m ingestion.profiler --data-dir data/raw/olist --out docs/profiling.md
"""
from __future__ import annotations

import argparse
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


# ── Per-table metadata (primary keys, foreign keys, date columns) ─────────────
TABLE_META: dict[str, dict[str, Any]] = {
    "olist_orders_dataset": {
        "pk": ["order_id"],
        "fk": {"customer_id": "olist_customers_dataset.customer_id"},
        "date_cols": [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
        "grain": "one row per order_id",
    },
    "olist_order_items_dataset": {
        "pk": ["order_id", "order_item_id"],
        "fk": {
            "order_id": "olist_orders_dataset.order_id",
            "seller_id": "olist_sellers_dataset.seller_id",
            "product_id": "olist_products_dataset.product_id",
        },
        "date_cols": ["shipping_limit_date"],
        "grain": "one row per (order_id, order_item_id)",
    },
    "olist_order_payments_dataset": {
        "pk": ["order_id", "payment_sequential"],
        "fk": {"order_id": "olist_orders_dataset.order_id"},
        "date_cols": [],
        "grain": "one row per (order_id, payment_sequential)",
    },
    "olist_order_reviews_dataset": {
        "pk": ["review_id"],
        "fk": {"order_id": "olist_orders_dataset.order_id"},
        "date_cols": ["review_creation_date", "review_answer_timestamp"],
        "grain": "WARNING: review_id may not be unique – profile required",
    },
    "olist_customers_dataset": {
        "pk": ["customer_id"],
        "fk": {},
        "date_cols": [],
        "grain": "one row per customer_id; customer_unique_id groups repeat buyers",
    },
    "olist_sellers_dataset": {
        "pk": ["seller_id"],
        "fk": {},
        "date_cols": [],
        "grain": "one row per seller_id",
    },
    "olist_products_dataset": {
        "pk": ["product_id"],
        "fk": {},
        "date_cols": [],
        "grain": "one row per product_id",
    },
    "olist_geolocation_dataset": {
        "pk": ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"],
        "fk": {},
        "date_cols": [],
        "grain": "one row per (zip, lat, lng) – multiple rows per zip expected",
    },
    "product_category_name_translation": {
        "pk": ["product_category_name"],
        "fk": {},
        "date_cols": [],
        "grain": "one row per product_category_name",
    },
    "olist_marketing_qualified_leads_dataset": {
        "pk": ["mql_id"],
        "fk": {},
        "date_cols": ["first_contact_date"],
        "grain": "one row per mql_id",
    },
    "olist_closed_deals_dataset": {
        "pk": ["mql_id"],
        "fk": {
            "mql_id": "olist_marketing_qualified_leads_dataset.mql_id",
            "seller_id": "olist_sellers_dataset.seller_id",
        },
        "date_cols": ["won_date"],
        "grain": "one row per mql_id",
    },
}


def sha256_file(path: Path) -> str:
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def profile_table(df: pd.DataFrame, path: Path, meta: dict[str, Any]) -> dict[str, Any]:
    """Profile a single CSV and return a result dict with real numbers."""
    n_rows, n_cols = df.shape
    file_size_mb = path.stat().st_size / 1_048_576

    # ── Null counts ──────────────────────────────────────────────────────────
    null_counts = df.isnull().sum().to_dict()
    null_pct = {c: round(null_counts[c] / n_rows * 100, 2) for c in null_counts}

    # ── Primary key uniqueness ───────────────────────────────────────────────
    pk = meta.get("pk", [])
    pk_available = all(c in df.columns for c in pk)
    if pk_available and pk:
        pk_unique = int(df[pk].drop_duplicates().shape[0])
        pk_total = n_rows
        pk_is_unique = pk_unique == pk_total
        pk_dup_count = pk_total - pk_unique
    else:
        pk_unique = None
        pk_total = n_rows
        pk_is_unique = None
        pk_dup_count = None

    # ── Date ranges ─────────────────────────────────────────────────────────
    date_ranges: dict[str, dict[str, str]] = {}
    for col in meta.get("date_cols", []):
        if col in df.columns:
            parsed = pd.to_datetime(df[col], errors="coerce")
            date_ranges[col] = {
                "min": str(parsed.min()) if not parsed.isna().all() else "all null",
                "max": str(parsed.max()) if not parsed.isna().all() else "all null",
                "null_count": int(parsed.isna().sum()),
            }

    # ── Column dtypes ────────────────────────────────────────────────────────
    dtypes = {c: str(df[c].dtype) for c in df.columns}

    return {
        "path": str(path),
        "file_size_mb": round(file_size_mb, 2),
        "sha256": sha256_file(path),
        "n_rows": n_rows,
        "n_cols": n_cols,
        "grain": meta.get("grain", "unknown"),
        "columns": list(df.columns),
        "dtypes": dtypes,
        "null_counts": null_counts,
        "null_pct": null_pct,
        "pk": pk,
        "pk_unique": pk_unique,
        "pk_total": pk_total,
        "pk_is_unique": pk_is_unique,
        "pk_dup_count": pk_dup_count,
        "date_ranges": date_ranges,
    }


def check_orphan_fks(
    dfs: dict[str, pd.DataFrame],
    table_name: str,
    fk_meta: dict[str, str],
) -> dict[str, dict[str, int]]:
    """Check orphan foreign-key counts."""
    results: dict[str, dict[str, int]] = {}
    df = dfs.get(table_name)
    if df is None:
        return results
    for col, ref in fk_meta.items():
        ref_table, ref_col = ref.split(".")
        ref_df = dfs.get(ref_table)
        if ref_df is None or col not in df.columns or ref_col not in ref_df.columns:
            continue
        orphans = ~df[col].isin(ref_df[ref_col])
        results[col] = {
            "total": int(df[col].notna().sum()),
            "orphans": int(orphans.sum()),
        }
    return results


def write_profiling_md(profiles: dict[str, dict], orphans: dict[str, dict], out: Path) -> None:
    """Write the profiling results to a Markdown file."""
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# Olist Data Profiling",
        "",
        f"> Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"> Source: `data/raw/olist/`  ",
        "> All counts are real measurements from the actual CSV files.",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Table | Rows | Cols | File (MB) | PK Unique? | PK Duplicates |",
        "|-------|------|------|-----------|------------|---------------|",
    ]
    for name, p in profiles.items():
        pk_str = "✅" if p["pk_is_unique"] else (
            "⚠️ DUPLICATES" if p["pk_is_unique"] is False else "N/A"
        )
        dup = p["pk_dup_count"] if p["pk_dup_count"] is not None else "—"
        lines.append(
            f"| `{name}` | {p['n_rows']:,} | {p['n_cols']} "
            f"| {p['file_size_mb']} | {pk_str} | {dup} |"
        )

    lines += ["", "---", ""]

    for name, p in profiles.items():
        lines += [
            f"## {name}",
            "",
            f"**Grain:** {p['grain']}  ",
            f"**Rows:** {p['n_rows']:,}  **Cols:** {p['n_cols']}  "
            f"**File:** {p['file_size_mb']} MB  ",
            f"**SHA-256:** `{p['sha256']}`  ",
            "",
            f"**Primary key:** `{p['pk']}`  ",
        ]
        if p["pk_is_unique"] is not None:
            if p["pk_is_unique"]:
                lines.append(f"**PK unique:** ✅ ({p['pk_unique']:,} distinct / {p['pk_total']:,} rows)  ")
            else:
                lines.append(
                    f"**PK unique:** ⚠️ DUPLICATES — "
                    f"{p['pk_dup_count']:,} duplicate rows "
                    f"({p['pk_unique']:,} distinct / {p['pk_total']:,} rows)  "
                )

        lines += ["", "### Columns & Nulls", ""]
        lines.append("| Column | dtype | Null count | Null % |")
        lines.append("|--------|-------|------------|--------|")
        for col in p["columns"]:
            lines.append(
                f"| `{col}` | {p['dtypes'][col]} "
                f"| {p['null_counts'][col]:,} | {p['null_pct'][col]}% |"
            )

        if p["date_ranges"]:
            lines += ["", "### Date ranges", ""]
            lines.append("| Column | Min | Max | Nulls |")
            lines.append("|--------|-----|-----|-------|")
            for col, dr in p["date_ranges"].items():
                lines.append(
                    f"| `{col}` | {dr['min']} | {dr['max']} | {dr['null_count']:,} |"
                )

        # Orphan FK checks
        tbl_orphans = orphans.get(name, {})
        if tbl_orphans:
            lines += ["", "### Foreign-key orphan check", ""]
            lines.append("| FK column | Total non-null | Orphans | OK? |")
            lines.append("|-----------|---------------|---------|-----|")
            for col, counts in tbl_orphans.items():
                ok = "✅" if counts["orphans"] == 0 else f"⚠️ {counts['orphans']:,} orphans"
                lines.append(f"| `{col}` | {counts['total']:,} | {counts['orphans']:,} | {ok} |")

        lines += ["", "---", ""]

    out.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile Olist CSVs")
    parser.add_argument("--data-dir", default="data/raw/olist", help="Directory with CSV files")
    parser.add_argument("--out", default="docs/profiling.md", help="Output markdown file")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    out_path = Path(args.out)

    print(f"Profiling CSVs in {data_dir} …")

    # Load all dataframes first (needed for FK checks)
    dfs: dict[str, pd.DataFrame] = {}
    for csv_path in sorted(data_dir.glob("*.csv")):
        stem = csv_path.stem
        print(f"  Loading {csv_path.name} …")
        dfs[stem] = pd.read_csv(csv_path, low_memory=False)

    profiles: dict[str, dict] = {}
    for stem, df in dfs.items():
        meta = TABLE_META.get(stem, {"pk": [], "fk": {}, "date_cols": [], "grain": "unknown"})
        csv_path = data_dir / f"{stem}.csv"
        print(f"  Profiling {stem} ({len(df):,} rows) …")
        profiles[stem] = profile_table(df, csv_path, meta)

    # FK orphan checks
    orphans: dict[str, dict] = {}
    for stem, meta in TABLE_META.items():
        fk = meta.get("fk", {})
        if fk:
            orphans[stem] = check_orphan_fks(dfs, stem, fk)

    write_profiling_md(profiles, orphans, out_path)
    print(f"\n✅ Profiling written to {out_path}")

    # Print a quick summary to stdout
    print("\n=== Key findings ===")
    for name, p in profiles.items():
        if p["pk_is_unique"] is False:
            print(f"  ⚠️  {name}: {p['pk_dup_count']:,} duplicate PK rows ({p['pk']})")
    print("  Full details in", out_path)


if __name__ == "__main__":
    main()
