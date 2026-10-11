# CommercePulse – Build Progress

> **If continuing in a new session**: read this file first, then resume from "Next up".

## Status

| Phase | Name | Status | Gate |
|-------|------|--------|------|
| 0 | Setup | ✅ Complete | `make test` passes |
| 1 | Profile + Contracts | 🔄 In Progress | — |
| 2 | Source DB + Bronze | ⏳ Pending | — |
| 3 | Silver (Iceberg) | ⏳ Pending | — |
| 4 | Gold (dbt) | ⏳ Pending | — |
| 5 | Airflow + Publication | ⏳ Pending | — |
| 6 | Failure Injection | ⏳ Pending | — |
| 7 | CI + Docs + v1.0 | ⏳ Pending | — |
| 8 | Cloud run | 🔒 Deferred (explicit auth required) | — |
| 9 | Kafka events | ⏳ Pending (v2) | — |
| 10 | ClickHouse benchmark | ⏳ Pending (v2) | — |
| 11 | AI incident assistant | ⏳ Pending (v2) | — |
| 12 | Terraform | ⏳ Pending (v2) | — |

## Phase 0 – Completed

**What was done:**
- Git initialized, connected to `suraj991/commercepulse-lakehouse`
- `.gitignore` (raw CSVs, secrets, Python/dbt artifacts)
- `.env.example` (all config keys, no secrets)
- `pyproject.toml` (ruff, pytest, all dependencies declared)
- `.pre-commit-config.yaml` (ruff, ruff-format, yaml/json/toml checks, secret detection)
- `infra/docker-compose.yml` – profiles: `core` (Postgres + MinIO), `airflow`, `kafka`, `clickhouse`, `all`
- `Makefile` – targets: `up`, `up-airflow`, `up-kafka`, `seed`, `extract`, `silver`, `dbt-build`, `test`, `demo`, `pipeline`, `down`, `clean`
- Python packages: `ingestion/`, `lakehouse/`, `replay/`, `tests/`
- `tests/test_smoke.py` – two passing smoke tests
- `benchmarks/results.md` – initialized
- Project directory structure created

**Gate result:** `make test` runs and `test_smoke` + `test_imports` pass (2 tests).

**Data:** All 11 Olist CSVs moved to `data/raw/olist/` (gitignored).

## Next up

**Phase 1: Profile + Contracts**
1. Run profiling script on all 11 CSVs → `docs/profiling.md`
2. Write `contracts/sources/*.yml` (columns, types, keys, nullability per table)
3. Write `contracts/metrics.yml` (5 business metrics with owner, definition, grain, exclusions)
4. Gate: profiling output documents each table's grain and any review_id duplicate issues

## Open Issues

- None (Phase 0 complete)

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| docker-compose profiles (`core`, `airflow`, `kafka`, `clickhouse`) | Lets developers bring up only what they need; avoids Airflow overhead for simple runs |
| ruff for lint + format | Replaces black + isort + flake8 with one fast tool |
| dbt-duckdb for local gold | Zero infrastructure required for local dbt runs; same SQL works on Snowflake with adapter macros |
| Raw CSVs in `data/raw/olist/` (gitignored) | Files are large (~50 MB total); test fixtures live in `tests/fixtures/` |

## Deferred / Unverified

- **Phase 8 cloud run**: AWS Glue, Athena, Snowflake – deferred until explicit authorization.
  Required: `make up` then authorize cloud credentials in `.env`.
- **Snowflake dbt-snowflake adapter**: installed via `pip install commercepulse[cloud]` only.
- **`terraform apply`**: Terraform config will be written in Phase 12 but not applied without authorization.
