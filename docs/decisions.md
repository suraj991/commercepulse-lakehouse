# CommercePulse – Architecture Decisions

## ADR-001: Idempotent bronze extraction via run_id ledger

**Status**: Accepted
**Date**: 2026-10-10

### Context
Bronze extraction runs on a schedule. Re-running after a partial failure should not create duplicate data.

### Decision
Each extraction records a ledger entry `{run_id, table, file_hash, row_count, ...}` as a JSON object in MinIO `_ledger/` prefix. A second call with the same `run_id` + `table` key is a no-op.

### Consequences
- Reruns are safe: idempotent by design.
- `run_id` is auto-generated (UUID short) per run, or caller-supplied for replay.
- Trade-off: ledger scan is O(n entries); acceptable for daily batch.

---

## ADR-002: Parquet bridge between Iceberg silver and dbt gold

**Status**: Accepted
**Date**: 2026-10-10

### Context
dbt with DuckDB adapter cannot read Iceberg Hadoop catalogs directly. Options considered:
1. Use Iceberg REST catalog — requires extra infra (Nessie/Polaris)
2. Export to Parquet — simple, no extra services
3. Read from MinIO directly — requires S3 credentials in dbt profiles

### Decision
`export_snapshot.py` exports each silver Iceberg table to `data/gold_input/{table}/snapshot_{id}/data.parquet`. dbt staging models read from this path with `read_parquet('.../**/data.parquet')`.

### Consequences
- No extra catalog service needed.
- Snapshot ID in path provides lineage: which Iceberg snapshot fed each dbt run.
- Manifest JSON checksums enable tamper detection.
- Downside: extra export step; data is stale between silver writes.

---

## ADR-003: Fan-out prevention via pre-aggregation

**Status**: Accepted
**Date**: 2026-10-10

### Context
`fct_order_items` requires joining order items to `dim_seller_history`. A multi-item order from one seller, joined at item grain to a SCD2 dimension with multiple records in range, produces N×M rows (fan-out).

### Decision
`int_order_items_agg` aggregates order_items to `(order_id, seller_id)` grain before any dimension join. The result has exactly one row per (order, seller), eliminating the fan-out vector.

The dbt singular test `assert_no_fanout_order_items` enforces this invariant on every pipeline run.

### Consequences
- SUM(price) by seller is correct even when a seller has N SCD2 records.
- Item-level attributes (individual product IDs) are not available in `fct_order_items`; use `stg_order_items` for item-level analysis.

---

## ADR-004: SCD2 structure with single-record sellers

**Status**: Accepted
**Date**: 2026-10-10

### Context
Olist data is a historical snapshot with no change events. There is no seller attribute change history.

### Decision
Implement SCD2 structure (`seller_sk`, `valid_from`, `valid_to`, `is_current`) using fixed validity `[2000-01-01, 9999-12-31]`. Surrogate key is `md5(seller_id)` for stability across runs.

### Consequences
- SCD2 schema is production-ready: when a real CDC feed is added, new rows are inserted with narrower date ranges without breaking downstream joins.
- Currently all sellers have `is_current = true` and no history — this is honest given the source.
- `assert_scd2_no_overlap` test enforces no overlapping validity periods.

---

## ADR-005: Quality gate with configurable reconciliation threshold

**Status**: Accepted
**Date**: 2026-10-10

### Context
The Olist dataset has ~0.3% of delivered orders with payment reconciliation gaps > 0.01 BRL. These are real source data imperfections (payment installments, rounding), not pipeline bugs.

### Decision
Quality gate checks reconciliation failure rate against a configurable threshold (default 5%). Below threshold → surface as WARNING, allow publication. Above threshold → FAIL, block publication.

### Consequences
- Real source imperfections are surfaced, not hidden.
- Pipeline is not blocked by known source characteristics.
- A genuine pipeline bug (e.g., double-counting freight) would exceed 5% and correctly fail.

---

## ADR-006: PySpark 4.0 + Iceberg 1.12 JAR stack

**Status**: Accepted
**Date**: 2026-10-10

### Context
PySpark 3.5.x is incompatible with Python 3.13 on arm64 (macOS). Java reflection API changes broke the SparkContext constructor.

### Decision
Upgrade to PySpark 4.0.1 with matching JARs:
- `iceberg-spark-runtime-4.0_2.13-1.12.0.jar`
- `hadoop-aws-3.4.1.jar`
- `aws-sdk-v2-bundle-2.28.17.jar`

### Consequences
- PySpark 4.0 removes `Column.nullsLast()` — use `F.desc_nulls_last(col)` instead.
- Iceberg 1.x renames `committed_at` → `made_current_at` in `.history` table.
- All three JARs must be version-compatible (Hadoop AWS 3.4.1 requires SDK v2).
