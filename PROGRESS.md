# CommercePulse – Build Progress

> **If continuing in a new session**: read this file first, then resume from "Next up".

## Status

| Phase | Name | Status | Gate |
|-------|------|--------|------|
| 0 | Setup | ✅ Complete | `make test` 2/2 pass |
| 1 | Profile + Contracts | ✅ Complete | `docs/profiling.md` written with real numbers |
| 2 | Source DB + Bronze | ✅ Complete | 11 tables seeded, extraction idempotent, 10/10 tests pass |
| 3 | Silver (Iceberg) | ✅ Complete | 7 tables, 550,688 rows, all lake checks pass |
| 4 | Gold (dbt) | ✅ Complete | 14 models, 66/66 dbt tests pass (core) |
| 5 | Airflow + Publication | ✅ Complete | Quality gate + publication JSON written |
| 6 | Failure Injection | ✅ Complete | 17/17 failure injection tests pass |
| 7 | CI + Docs + v1.0 | ✅ Complete | GitHub Actions CI, README Mermaid, decisions.md, incident_report.md |
| 8 | Cloud run | 🔒 Deferred (explicit auth required) | — |
| 9 | Kafka events | ⏳ Pending (v2) | — |
| 10 | ClickHouse benchmark | ⏳ Pending (v2) | — |
| 11 | AI incident assistant | ⏳ Pending (v2) | — |
| 12 | Terraform | ⏳ Pending (v2) | — |

## Phase 7 – Completed 2026-10-10

**What was done:**
- `.github/workflows/ci.yml`: unit tests + dbt validate on every push/PR
- `README.md`: Mermaid architecture diagram, quick start, measured results, metric contracts table
- `docs/decisions.md`: 6 ADRs (bronze idempotency, Parquet bridge, fan-out, SCD2, quality gate threshold, PySpark stack)
- `docs/incident_report.md`: payment reconciliation incident (root cause: Olist installment payment gaps)
- `benchmarks/results.md`: real numbers for all phases

## Phase 6 – Completed 2026-10-10

**What was done:**
- `replay/injectors.py`: deterministic failure injectors (fixed seed via numpy RNG(42))
- `tests/test_failure_injection.py`: 8 scenarios × 17 assertions, 17/17 pass
  - Null PK, invalid enum, duplicate PK, bronze idempotency
  - Payment mismatch surfaced, fan-out detection, quality gate threshold, GMV cross-grain

## Phase 5 – Completed 2026-10-10

**What was done:**
- `orchestration/dags/dag_pipeline.py`: daily DAG (bronze → silver → export → FX → dbt → gate → publish)
- `orchestration/dags/dag_backfill.py`: parameterized backfill DAG (manual trigger)
- `scripts/quality_gate.py`: 3 checks; reconciliation warns at < 5% failure rate, fails above
- `scripts/publish.py`: writes publication JSON with metrics snapshot and publication_id
- First publication: `471b3257-1dfd-45a1-82a5-82a9bb6715c9`
  - 99,441 orders, 96,470 delivered, R$13,220,248.93 fulfilled GMV
  - 300/96,470 delivered orders (0.31%) have payment gaps > 0.01 BRL → WARN (Olist source characteristic)

## Phase 4 – Completed 2026-10-10

**What was done:**
- `warehouse/dbt/` initialized (dbt-core 1.12.5, dbt-duckdb 1.11.0, DuckDB 1.5.6)
- 10 staging models (read silver Parquet via `read_parquet()` glob)
- 2 intermediate models (`int_order_items_agg`, `int_payment_totals`)
- 2 dimension models (`dim_seller_history` SCD2, `dim_fx_rate` forward-fill)
- 4 mart models (`fct_orders`, `fct_payments`, `fct_order_items`, `fct_seller_leads`)
- 3 custom singular tests (`assert_no_fanout_order_items`, `assert_gmv_reconciliation`, `assert_scd2_no_overlap`)
- `scripts/backfill_fx.py`, `Makefile` targets: `dbt-deps`, `dbt-build-core`, `dbt-test`, `backfill-fx`
- **Note**: `stg_mql`, `stg_closed_deals`, `stg_product_category_translations` require `make silver export-gold` re-run
  (these tables were added to SILVER_TABLES in Phase 4)

**dbt build result:** 66/66 tests pass in 1.12s (core models; FX sparse until `make backfill-fx`)

## Phase 3 – Completed 2026-10-10

**What was done:**
- `lakehouse/silver_job.py`: PySpark 4.0 + Iceberg v2 silver job
- Validation (null PK/FK + enum checks), dedup (window ROW_NUMBER), reject tables
- Lake checks: row count + PK uniqueness after write
- Schema evolution demo: `_ingested_at` column added to sellers via ALTER TABLE
- Snapshot export: 7 tables → `data/gold_input/` with manifest.json
- JAR stack resolved: `iceberg-spark-runtime-4.0_2.13-1.12.0.jar` + `hadoop-aws-3.4.1.jar` + `aws-sdk-v2-bundle-2.28.17.jar`
- PySpark 4.0 API fixes: `F.desc_nulls_last()`, `made_current_at` in `.history`

**Silver results:** 550,688 rows, 7 tables, all lake checks passed, ~14s total

## Phase 2 – Completed 2026-10-10

**What was done:**
- `ingestion/seed.py`: loads 11 CSVs into Postgres, 1,559,764 rows (~71s)
- `ingestion/extractor.py`: idempotent bronze extraction with run_id ledger
- `ingestion/fx_client.py`: Frankfurter API with local JSON cache and lookback
- `tests/test_ingestion.py`: 10 tests (7 unit + 3 integration)

## Phase 1 – Completed 2026-10-10

**What was done:**
- `ingestion/profiler.py`: profiles all 11 CSVs → `docs/profiling.md`
- `contracts/metrics.yml`: 5 metric contracts (fulfilled_gmv, payment_reconciliation,
  seller_conversion, seller_gmv_attribution, observed_demand)

## Phase 0 – Completed 2026-10-10

**What was done:**
- Git init, `.gitignore`, `.env.example`, `pyproject.toml`, `.pre-commit-config.yaml`
- `infra/docker-compose.yml` – profiles: core/airflow/kafka/clickhouse/all
- `Makefile`, Python packages, `tests/test_smoke.py`, `benchmarks/results.md`

## Next up

**Phase 8 (deferred)**: Cloud run – requires explicit authorization for AWS/Snowflake credentials.

**Phase 9**: Kafka events (v2)
- `kafka_producer.py` – stream order events to Kafka topic `cp.orders`
- `kafka_consumer.py` – consume events, write to bronze real-time landing zone

**Phase 10**: ClickHouse benchmark (v2)
- Load `fct_orders` + `fct_order_items` into ClickHouse
- Benchmark query latency vs DuckDB for analytical queries

## Open Issues

- `stg_mql`, `stg_closed_deals`, `stg_product_category_translations` require `make silver export-gold`
  re-run with updated SILVER_TABLES (added in Phase 4). Run `make silver export-gold dbt-build` to fix.
- FX rates: only 2 dates cached. Run `make backfill-fx` to populate 2016–2018 range.
  Until then, `fct_orders.gmv_usd` is NULL for all orders.

## Deferred / Unverified

- **Phase 8 cloud run**: AWS Glue, Athena, Snowflake – deferred until explicit authorization.
- **Snowflake dbt-snowflake adapter**: installed via `pip install commercepulse[cloud]` only.
- **`terraform apply`**: Terraform config will be written in Phase 12 but not applied without authorization.
