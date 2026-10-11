# CommercePulse – Benchmark Results

All measurements are real runs. Unexecuted steps are marked **not measured**.

## Format

| Date | Phase | Command / Step | Data Volume | Duration | Result | Machine |
|------|-------|----------------|-------------|----------|--------|---------|

---

## Phase 0

| Date | Phase | Step | Notes |
|------|-------|------|-------|
| 2026-10-10 | 0 | `make test` | 2/2 tests pass (test_smoke, test_imports) |

## Phase 2

| Date | Phase | Step | Data Volume | Duration | Result |
|------|-------|------|-------------|----------|--------|
| 2026-10-10 | 2 | `make seed` (Postgres load) | 11 tables, 1,559,764 rows total | ~71s | 11/11 tables loaded |
| 2026-10-10 | 2 | Bronze extraction (run 1) | 11 tables → MinIO Parquet | ~4s | 11 files written |
| 2026-10-10 | 2 | Bronze extraction (run 2, same run_id) | same run_id | <1s | 0 tables extracted (idempotent) ✅ |
| 2026-10-10 | 2 | Unit + integration tests | 10 tests | <2s | 10/10 pass ✅ |

### Seed row counts (measured 2026-10-10)
| Table | Rows | Duration |
|-------|------|----------|
| olist.orders | 99,441 | 6.7s |
| olist.order_items | 112,650 | 6.3s |
| olist.order_payments | 103,886 | 4.1s |
| olist.order_reviews | 99,224 | 5.5s |
| olist.customers | 99,441 | 3.7s |
| olist.sellers | 3,095 | 0.1s |
| olist.products | 32,951 | 2.3s |
| olist.geolocation | 1,000,163 | 42.0s |
| olist.product_category_translations | 71 | 0.0s |
| marketing.mql | 8,000 | 0.3s |
| marketing.closed_deals | 842 | 0.1s |

---

## Phase 1 (profiling)

_Results will be written here after `make profile` runs._

---

## Phase 3 (silver layer)

| Date | Table | Bronze Rows | Valid | Rejected | Deduped | Duration |
|------|-------|-------------|-------|----------|---------|----------|
| 2026-10-10 | orders | 99,441 | 99,441 | 0 | 99,441 | 7.2s |
| 2026-10-10 | order_items | 112,650 | 112,650 | 0 | 112,650 | 1.5s |
| 2026-10-10 | order_payments | 103,886 | 103,886 | 0 | 103,886 | 1.1s |
| 2026-10-10 | order_reviews | 99,224 | 99,224 | 0 | 99,224 | 1.3s |
| 2026-10-10 | customers | 99,441 | 99,441 | 0 | 99,441 | 1.0s |
| 2026-10-10 | sellers | 3,095 | 3,095 | 0 | 3,095 | 0.5s |
| 2026-10-10 | products | 32,951 | 32,951 | 0 | 32,951 | 0.6s |

Lake checks: **all passed** (550,688 rows, 7 tables)
Schema evolution: sellers `_ingested_at` column added; old snapshot (5249430885397119951) confirmed no new column.
Snapshot export: 7 tables → data/gold_input/ with manifest.json (checksums recorded)

Stack: PySpark 4.0.1, Iceberg 1.12 (iceberg-spark-runtime-4.0_2.13-1.12.0.jar), Hadoop-AWS 3.4.1, AWS SDK v2 2.28.17

## Phase 4 (dbt gold layer)

| Date | Step | Models | Tests | Duration | Result |
|------|------|--------|-------|----------|--------|
| 2026-10-10 | `make dbt-build-core` | 14 models (7 stg views, 2 int views, 2 dim tables, 3 mart tables) | 66 tests | 1.12s | 66/66 pass ✅ |

Custom singular tests:
- `assert_no_fanout_order_items`: PASS — 0 rows returned (no fan-out duplicates)
- `assert_gmv_reconciliation`: PASS — 0 orders exceed 0.01 BRL GMV gap
- `assert_scd2_no_overlap`: PASS — 0 overlapping seller validity periods

Notes:
- `stg_mql`, `stg_closed_deals`, `stg_product_category_translations` require `make silver export-gold` re-run (tables added to SILVER_TABLES in Phase 4)
- `dim_fx_rate`: 2 rows (only 2018-05-13 and 2018-05-15 cached); `gmv_usd` NULL for all orders until `make backfill-fx` runs
- Stack: dbt-core 1.12.5, dbt-duckdb 1.11.0, DuckDB 1.5.6

---

## Phase 5 (Airflow orchestration + quality gate)

### Manual Airflow DAG run (2026-10-11, run_id: manual_run_20261010)

All 7 tasks reached **success**:

| Task | Attempts | Start (UTC) | End (UTC) | Duration |
|------|----------|-------------|-----------|----------|
| bronze_extract | 4 | 05:51:24 | 05:51:48 | 24s |
| silver_job | 5 | 06:13:35 | 06:15:41 | 2m 6s |
| export_snapshot | 1 | 06:15:41 | 06:16:17 | 36s |
| backfill_fx | 1 | 06:16:18 | 06:28:10 | 11m 52s |
| dbt_build | 5 | 06:43:17 | 06:43:23 | 6s |
| quality_gate | 1 | 06:43:23 | 06:43:24 | <1s |
| publish_report | 1 | 06:43:24 | 06:43:25 | <1s |

**End-to-end wall-clock runtime: 52m 1s** (first task start to last task end, inclusive of retry wait times)
**Happy-path runtime (no retries): ~15 min** (sum of successful task durations)

Bugs fixed during this run:
- `ingestion/extractor.py`: pandas 2.3 removed `Engine`/`Connection` from `pd.read_sql`; bypassed with `conn.execute(text(...))` + `pd.DataFrame(rows.mappings().all())`
- `lakehouse/spark_session.py`: `Path.resolve()` inside Docker Desktop returned macOS host path via VirtioFS; fixed by removing `.resolve()`
- `lakehouse/export_snapshot.py`: stale `snapshot_*` dirs caused duplicate Parquet reads by dbt; fixed with pre-write cleanup
- `warehouse/dbt/models/staging/stg_fx_rates.sql`: weekend JSON files share `"date"` with their last trading day, causing uniqueness test failures; fixed with `SELECT DISTINCT`
- `warehouse/dbt/models/marts/fct_seller_leads.sql`: `GROUP BY l.origin` vs `coalesce(l.origin, 'unknown')` produced two 'unknown' rows; fixed to `GROUP BY coalesce(l.origin, 'unknown')`
- `orchestration/dags/dag_pipeline.py`: added `max_active_runs=1` to prevent concurrent scheduled catch-up runs competing for the DuckDB file lock

| Date | Step | Result |
|------|------|--------|
| 2026-10-10 | Quality gate (`scripts/quality_gate.py`) | PASSED ✅ |
| 2026-10-10 | Publication (`scripts/publish.py`) | publication_id: 471b3257-1dfd-45a1-82a5-82a9bb6715c9 |

Quality gate findings:
- payment_reconciliation: ⚠️ 300/96,470 delivered orders (0.31%) have gap > 0.01 BRL (known Olist source issue; rate < 5% threshold → WARN not FAIL)
- fulfilled_gmv: ✅ 96,470 delivered orders, R$13,220,248.93 total fulfilled GMV
- scd2_uniqueness: ✅ all 3,095 seller_sk values unique

---

## Phase 6 (failure injection)

| Date | Step | Tests | Duration | Result |
|------|------|-------|----------|--------|
| 2026-10-10 | `pytest tests/test_failure_injection.py -v` | 17 tests (8 scenarios, 17 assertions) | 2.62s | 17/17 pass ✅ |
| 2026-10-10 | Full unit test suite (`-m "not integration"`) | 26 tests | 0.69s | 26/26 pass ✅ |

Scenarios covered:
1. Null PK injection: rejected with reason `null:order_id`
2. Invalid enum injection: `order_status="refunded"` rejected
3. Duplicate PK dedup: 1 row removed, 5 remain
4. Bronze ledger idempotency: same run_id skipped, different run_ids both process
5. Payment mismatch surfaced: gap detected, not zeroed
6. Fan-out detection: direct join multiplies rows; pre-aggregation prevents it
7. Quality gate threshold: 0.3% → warn; 10% → fail; 5% → pass (strict >)
8. GMV cross-grain reconciliation: order grain = seller grain; injected mismatch detected

---

## Phase 10 (ClickHouse benchmark)

_Results will be written here after Phase 10 executes._

---

## Cloud (Phase 8 – deferred)

Cloud jobs not yet authorized. All cloud metrics: **not measured**.
