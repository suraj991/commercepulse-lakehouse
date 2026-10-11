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

## Phase 6 (failure injection)

_Results will be written here after `make test-failure` runs._

---

## Phase 10 (ClickHouse benchmark)

_Results will be written here after Phase 10 executes._

---

## Cloud (Phase 8 – deferred)

Cloud jobs not yet authorized. All cloud metrics: **not measured**.
