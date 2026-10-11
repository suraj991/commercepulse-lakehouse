"""CommercePulse daily pipeline DAG.

Task chain:
  bronze_extract → silver_job → export_snapshot → backfill_fx
  → dbt_build → quality_gate → publish_report

The project root is mounted at /opt/commercepulse in the Airflow container.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

CP_HOME = "/opt/commercepulse"
PYTHON = "python3"

_default_args = {
    "owner": "commercepulse",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="commercepulse_pipeline",
    description="CommercePulse: bronze → silver → gold → quality gate → publish",
    schedule="0 6 * * *",          # 06:00 UTC daily
    start_date=datetime(2026, 10, 1),
    catchup=False,
    max_active_runs=1,
    default_args=_default_args,
    tags=["commercepulse", "pipeline"],
    doc_md="""
### CommercePulse Pipeline

Full local pipeline: Postgres → MinIO (bronze) → Iceberg (silver) → Parquet
→ dbt/DuckDB (gold) → quality gate → publication record.

**On failure**: the task retries once after 5 minutes. If the quality gate
fails the pipeline stops and no publication record is written.
""",
) as dag:

    bronze_extract = BashOperator(
        task_id="bronze_extract",
        bash_command=f"{PYTHON} -m ingestion.extractor",
        cwd=CP_HOME,
    )

    silver_job = BashOperator(
        task_id="silver_job",
        bash_command=f"{PYTHON} -m lakehouse.silver_job",
        cwd=CP_HOME,
    )

    export_snapshot = BashOperator(
        task_id="export_snapshot",
        bash_command=f"{PYTHON} -m lakehouse.export_snapshot",
        cwd=CP_HOME,
    )

    backfill_fx = BashOperator(
        task_id="backfill_fx",
        bash_command=f"{PYTHON} scripts/backfill_fx.py",
        cwd=CP_HOME,
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command="dbt build --profiles-dir . --target local",
        cwd=f"{CP_HOME}/warehouse/dbt",
    )

    quality_gate = BashOperator(
        task_id="quality_gate",
        bash_command=f"{PYTHON} scripts/quality_gate.py",
        cwd=CP_HOME,
        # Exit code 1 fails the task and blocks publish_report.
    )

    publish_report = BashOperator(
        task_id="publish_report",
        bash_command=(
            f"{PYTHON} scripts/publish.py"
            " --run-id {{ run_id }}"
            " --dag-run-date {{ ds }}"
        ),
        cwd=CP_HOME,
    )

    (
        bronze_extract
        >> silver_job
        >> export_snapshot
        >> backfill_fx
        >> dbt_build
        >> quality_gate
        >> publish_report
    )
