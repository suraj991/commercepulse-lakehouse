# CommercePulse Makefile
# Usage: make <target>
# All docker-compose commands use the infra/ directory.

COMPOSE = docker compose -f infra/docker-compose.yml
PYTHON  = python3
DBT     = dbt
CP_DIR  = $(shell pwd)

.PHONY: help up up-airflow up-kafka down seed test test-unit test-integration \
        profile lint format pre-commit-install demo docs-serve clean

# ─── Default ──────────────────────────────────────────────────────────────────
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Infrastructure ───────────────────────────────────────────────────────────
up: ## Start core services (Postgres + MinIO)
	@cp -n .env.example .env 2>/dev/null || true
	$(COMPOSE) --profile core up -d
	@echo "Waiting for services..."
	@sleep 3
	@echo "Postgres:  localhost:5432"
	@echo "MinIO API: http://localhost:9000  (console: http://localhost:9001)"

up-airflow: up ## Start core + Airflow services
	$(COMPOSE) --profile airflow up -d
	@echo "Airflow:   http://localhost:8080  (admin/admin)"

up-kafka: up ## Start core + Kafka services (Phase 9)
	$(COMPOSE) --profile kafka up -d

up-clickhouse: up ## Start core + ClickHouse (Phase 10)
	$(COMPOSE) --profile clickhouse up -d

down: ## Stop and remove all containers (keeps volumes)
	$(COMPOSE) --profile all down

down-volumes: ## Stop containers AND delete volumes (destructive!)
	$(COMPOSE) --profile all down -v

# ─── Data ─────────────────────────────────────────────────────────────────────
seed: ## Seed Postgres with Olist data
	$(PYTHON) -m ingestion.seed --data-dir data/raw/olist

profile: ## Profile all CSVs and write docs/profiling.md
	$(PYTHON) -m ingestion.profiler --data-dir data/raw/olist --out docs/profiling.md

extract: ## Run bronze extraction (Postgres → MinIO Parquet)
	$(PYTHON) -m ingestion.extractor

silver: ## Run PySpark silver job (bronze → Iceberg)
	$(PYTHON) -m lakehouse.silver_job

export-gold: ## Export silver Iceberg snapshot → Parquet for dbt
	$(PYTHON) -m lakehouse.export_snapshot

# ─── dbt ──────────────────────────────────────────────────────────────────────
dbt-deps: ## Install dbt packages
	cd warehouse/dbt && $(DBT) deps --profiles-dir .

dbt-build-core: ## dbt build excluding tables that need silver re-export (mql, closed_deals, product_category_translations)
	cd warehouse/dbt && $(DBT) build --profiles-dir . --target local \
	  --exclude stg_mql stg_closed_deals stg_product_category_translations fct_seller_leads

dbt-build: ## dbt build (DuckDB local) — requires full silver+export-gold first
	cd warehouse/dbt && $(DBT) build --profiles-dir . --target local

dbt-test: ## Run only dbt tests
	cd warehouse/dbt && $(DBT) test --profiles-dir . --target local

dbt-docs: ## Generate and serve dbt docs
	cd warehouse/dbt && $(DBT) docs generate --profiles-dir . && $(DBT) docs serve

backfill-fx: ## Backfill BRL/USD FX rates for the Olist date range (2016-2018)
	$(PYTHON) scripts/backfill_fx.py

# ─── Tests ────────────────────────────────────────────────────────────────────
test: ## Run all tests
	$(PYTHON) -m pytest tests/ -v

test-unit: ## Run only unit tests (no services needed)
	$(PYTHON) -m pytest tests/ -v -m "not integration and not cloud and not slow"

test-integration: ## Run integration tests (requires running services)
	$(PYTHON) -m pytest tests/ -v -m "integration"

test-failure: ## Run Phase 6 failure injection tests
	$(PYTHON) -m pytest tests/test_failure_injection.py -v

# ─── Quality ──────────────────────────────────────────────────────────────────
lint: ## Lint with ruff
	ruff check .

format: ## Format with ruff
	ruff format .

pre-commit-install: ## Install pre-commit hooks
	pre-commit install

pre-commit-run: ## Run pre-commit on all files
	pre-commit run --all-files

# ─── Demo (Phase 7 gate) ──────────────────────────────────────────────────────
demo: ## Run full local demo: trace metric → inject bad data → publish blocked → recover
	$(PYTHON) scripts/demo.py

# ─── Full local pipeline ──────────────────────────────────────────────────────
pipeline: seed extract silver export-gold backfill-fx dbt-deps dbt-build ## Run the full local pipeline end-to-end

# ─── Cleanup ─────────────────────────────────────────────────────────────────
clean: ## Remove Python artifacts and dbt targets
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
	rm -rf warehouse/dbt/target warehouse/dbt/dbt_packages
