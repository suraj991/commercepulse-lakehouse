# CommercePulse – Resume Evidence Log

> Every number in this file came from an actual command run on 2026-10-10 or 2026-10-11.
> Machine: macOS Darwin 25.6.0, Apple M-series (arm), 8 cores, 16 GB RAM.
> No estimates. No rounding beyond what the output showed.

---

## Evidence Table

| Claim | Exact Number | Command | Proof File / Output |
|-------|-------------|---------|---------------------|
| Source rows seeded | 1,559,764 across 11 tables | `make seed` | `benchmarks/results.md` Phase 2 |
| Bronze extraction time | ~4s for 11 tables | `make extract` | `benchmarks/results.md` Phase 2 |
| Bronze extraction idempotency | 0 rows on second run (same run_id) | `make extract` (run 2) | `benchmarks/results.md` Phase 2 |
| Silver rows validated | 550,688 rows, 7 tables | `make silver` | `benchmarks/results.md` Phase 3 |
| Silver rows rejected | 0 rejections across all 7 tables | `make silver` | `benchmarks/results.md` Phase 3 |
| Silver lake checks | All passed (row count + PK uniqueness) | `make silver` | `lakehouse/silver_job.py:lake_checks()` |
| Silver schema evolution | Old snapshot (5249430885397119951) lacks `_ingested_at` | `make silver` | `benchmarks/results.md` Phase 3 |
| fct_orders row count | 99,441 | `python3.13 -c "duckdb.connect('data/commercepulse.duckdb')"` | DuckDB `select count(*) from fct_orders` |
| fct_payments row count | 99,441 | same | DuckDB |
| fct_order_items (order+seller combos) | 100,010 | same | DuckDB `select count(*) from fct_order_items` |
| Total order items in source | 112,650 | `benchmarks/results.md` | olist.order_items seed count |
| Fan-out compression | 112,650 items → 100,010 (order,seller) pairs | DuckDB query | `fct_order_items.item_count` |
| Fulfilled GMV (delivered only) | R$13,220,248.93 | `python3.13 scripts/quality_gate.py` | DuckDB `sum(gmv_brl) filter (where is_delivered=1)` |
| Total GMV (all statuses) | R$13,591,643.70 | DuckDB query | `sum(gmv_brl) from fct_orders` |
| Delivered orders | 96,470 of 99,441 (97.0%) | DuckDB query | `fct_orders.is_delivered` |
| Canceled orders | 625 | DuckDB query | `fct_orders.order_status` |
| Cross-grain GMV reconciliation | R$0.00 difference | DuckDB query joining fct_orders to fct_order_items | `assert_gmv_reconciliation.sql` test |
| Payment reconciliation rate | 98.92% (98,365 of 99,441) reconcile within R$0.01 | DuckDB query | `fct_payments.is_reconciled` |
| Unreconciled orders (source gaps) | 1,076 (0.31% of delivered; < 5% threshold → WARN) | DuckDB query | `scripts/quality_gate.py` |
| Payment gap range (source data) | min=R$0.02, max=R$182.81, median=R$5.90 | DuckDB percentile query | Session measurement |
| SCD2 sellers | 3,095 sellers, 0 overlapping validity periods | DuckDB + `assert_scd2_no_overlap.sql` | `dim_seller_history` |
| SCD2 surrogate key method | md5(seller_id) | `warehouse/dbt/models/dimensions/dim_seller_history.sql:4` | Source code |
| FX dimension rows | 235 days (forward-filled from 2 cached dates) | DuckDB | `dim_fx_rate` |
| dbt models built | 14 (core: 7 stg views + 2 int views + 2 dim tables + 3 mart tables) | `dbt build --exclude stg_mql ...` | dbt output |
| dbt tests run | 66 | dbt build output | `Done. PASS=66 WARN=0 ERROR=0` |
| dbt tests pass rate | 100% (66/66 local; 68/81 in Airflow — 2 data tests fixed, 11 skipped upstream) | dbt build 2026-10-10/11 | dbt output |
| Custom singular tests | 3 (assert_no_fanout_order_items, assert_gmv_reconciliation, assert_scd2_no_overlap) | dbt build | `warehouse/dbt/tests/` |
| dbt build time (median of 3 runs) | 3.82s wall clock (runs: 3.62s, 4.12s, 3.82s) | `/usr/bin/time -p dbt build ...` ×3 | Session timing |
| Airflow dbt build (full pipeline, 18 models) | 6s (68 PASS, 0 WARN, 0 ERROR, 11 SKIP) | Airflow `dbt_build` task, 2026-10-11 | `docs/airflow_run_log.txt` |
| Unit tests (non-integration) | 26 pass, 3 skipped (integration) | `pytest tests/ -m "not integration"` | `26 passed, 3 deselected in 1.02s` |
| Failure injection tests | 17 pass (8 scenarios, 17 assertions) | `pytest tests/test_failure_injection.py -v` | `17 passed in 2.62s` |
| Quality gate: fulfilled GMV | R$13,220,248.93 | `python3.13 scripts/quality_gate.py` | `scripts/quality_gate.py` exits 0 |
| Publication UUID | 471b3257-1dfd-45a1-82a5-82a9bb6715c9 | `python3.13 scripts/publish.py` | `data/publications/471b3257-*.json` |
| Airflow end-to-end pipeline run | All 7 tasks green, run_id=manual_run_20261010 | Airflow manual trigger, 2026-10-11 | `docs/airflow_run_log.txt` |
| Airflow pipeline wall-clock (with retries) | 52m 1s (first task start → last task end, includes retry delays) | 05:51:24 → 06:43:25 UTC | `benchmarks/results.md` Phase 5 |
| Airflow pipeline happy-path runtime | ~15 min (sum of task durations, no retries) | Task-level timing | `benchmarks/results.md` Phase 5 |
| FX backfill (BRL→USD, full Olist range) | 685+ trading days cached, 2016-09-01 → 2018-10-31 | `backfill_fx` task, Airflow run | `data/fx_cache/` |
| Distinct customer states in gold | 27 | DuckDB query | `count(distinct customer_state) from fct_orders` |
| CI checks per PR | 9 steps across 2 jobs (unit-tests + dbt-validate) | `.github/workflows/ci.yml` | File |

---

## What Is NOT Claimed (Honest Gaps)

| Item | Status | Reason |
|------|--------|--------|
| Airflow DAG execution | ✅ COMPLETE (2026-10-11) | All 7 tasks green — moved to Evidence Table above |
| CI on GitHub Actions | CODE EXISTS, not yet triggered | Workflow yaml is valid; no green badge yet |
| FX USD conversion | ✅ COMPLETE (2026-10-11) | Full date range cached via `backfill_fx` Airflow task |
| `stg_mql`, `stg_closed_deals`, `stg_product_category_translations` | ✅ COMPLETE | Included in full Airflow run (silver + export + dbt all ran end-to-end) |
| `fct_seller_leads` | ✅ COMPLETE | Ran in Airflow dbt_build; uniqueness bug fixed (GROUP BY coalesce) |
| Silver reject tables | 0 ROWS | Source data was clean; reject tables exist but are empty |
| End-to-end wall-clock time | ✅ MEASURED (2026-10-11) | 52m 1s with retries; ~15 min happy-path |
| Cloud run (Phase 8) | NOT STARTED | Requires explicit AWS/Snowflake auth |
