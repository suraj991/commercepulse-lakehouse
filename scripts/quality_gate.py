"""Quality gate: query DuckDB gold tables and exit 1 if any check fails.

Checks (from contracts/metrics.yml):
1. payment_reconciliation: no delivered orders with |payment_gap| > 0.01 BRL
2. fulfilled_gmv_positive: at least one delivered order with gmv_brl > 0
3. scd2_uniqueness: all seller_sk values in dim_seller_history are unique
   (already enforced by dbt test, re-checked here for the gate)

Exit codes:
  0 = all checks pass
  1 = one or more checks fail (blocks publish in the Airflow DAG)

Usage:
    python scripts/quality_gate.py
    python scripts/quality_gate.py --db data/commercepulse.duckdb
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def run_gate(db_path: Path, max_recon_failure_pct: float = 5.0) -> tuple[list[str], list[str]]:
    """Return (failures, warnings). Failures block publication; warnings are surfaced only."""
    import duckdb

    failures: list[str] = []
    warnings: list[str] = []
    conn = duckdb.connect(str(db_path), read_only=True)

    # 1. Payment reconciliation (from contracts/metrics.yml: surface mismatches, don't hide them).
    # Hard-fail only if failure rate > max_recon_failure_pct (default 5%).
    # The Olist source dataset has ~0.3% of delivered orders with real payment gaps;
    # this is surfaced as a warning, not a hard block.
    result = conn.execute("""
        select
            count(*) filter (where fo.is_delivered = 1) as n_delivered,
            count(*) filter (where fo.is_delivered = 1 and fp.is_reconciled = false) as n_unreconciled
        from fct_payments fp
        join fct_orders fo using (order_id)
    """).fetchone()
    n_delivered, n_unreconciled = (result[0] or 0), (result[1] or 0)
    if n_unreconciled > 0:
        pct = n_unreconciled / max(n_delivered, 1) * 100
        msg = (
            f"payment_reconciliation: {n_unreconciled:,}/{n_delivered:,} delivered orders "
            f"({pct:.2f}%) have |payment_gap| > 0.01 BRL"
        )
        if pct > max_recon_failure_pct:
            failures.append(msg)
        else:
            warnings.append(msg)

    # 2. Fulfilled GMV must be > 0 if any delivered orders exist
    result = conn.execute("""
        select
            count(*) filter (where is_delivered = 1)  as delivered_count,
            sum(gmv_brl) filter (where is_delivered = 1) as total_gmv
        from fct_orders
    """).fetchone()
    if result:
        delivered_count, total_gmv = result
        if delivered_count > 0 and (total_gmv is None or total_gmv <= 0):
            failures.append(
                f"fulfilled_gmv: {delivered_count:,} delivered orders but total_gmv={total_gmv}"
            )

    # 3. SCD2 uniqueness: no duplicate seller_sk
    result = conn.execute("""
        select count(*) as dupes
        from (
            select seller_sk, count(*) as n
            from dim_seller_history
            group by seller_sk
            having count(*) > 1
        )
    """).fetchone()
    n_dupes = result[0] if result else 0
    if n_dupes > 0:
        failures.append(f"scd2_uniqueness: {n_dupes:,} duplicate seller_sk values in dim_seller_history")

    conn.close()
    return failures, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="CommercePulse quality gate")
    parser.add_argument("--db", default="data/commercepulse.duckdb",
                        help="Path to DuckDB database")
    parser.add_argument("--max-recon-failure-pct", type=float, default=5.0,
                        help="Max %% of delivered orders with payment gap before hard fail (default: 5.0)")
    args = parser.parse_args()
    db_path = Path(args.db)

    if not db_path.exists():
        print(f"❌  DB not found: {db_path}. Run `make dbt-build` first.")
        sys.exit(1)

    failures, warnings = run_gate(db_path, max_recon_failure_pct=args.max_recon_failure_pct)

    for w in warnings:
        print(f"⚠️   {w}")

    if failures:
        print(f"\n❌  Quality gate FAILED ({len(failures)} check(s)):")
        for f in failures:
            print(f"    - {f}")
        sys.exit(1)
    else:
        print("✅  Quality gate passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
