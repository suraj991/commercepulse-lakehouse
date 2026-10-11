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

## Phase 6 (failure injection)

_Results will be written here after `make test-failure` runs._

---

## Phase 10 (ClickHouse benchmark)

_Results will be written here after Phase 10 executes._

---

## Cloud (Phase 8 – deferred)

Cloud jobs not yet authorized. All cloud metrics: **not measured**.
