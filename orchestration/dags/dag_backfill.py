"""CommercePulse historical backfill DAG.

Parameterized: trigger manually with start_date / end_date / tables.

Example trigger via CLI:
    airflow dags trigger commercepulse_backfill \\
        --conf '{"start_date": "2017-01-01", "end_date": "2017-12-31"}'
"""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.bash import BashOperator

CP_HOME = "/opt/commercepulse"
PYTHON = "python3"

_default_args = {
    "owner": "commercepulse",
    "retries": 0,
    "email_on_failure": False,
}

with DAG(
    dag_id="commercepulse_backfill",
    description="Backfill bronze extraction + silver for a given date range",
    schedule=None,                  # triggered manually
    start_date=datetime(2026, 10, 1),
    catchup=False,
    default_args=_default_args,
    params={
        "start_date": Param("2017-01-01", type="string", description="Start date YYYY-MM-DD"),
        "end_date":   Param("2017-12-31", type="string", description="End date YYYY-MM-DD (exclusive)"),
        "tables":     Param(
            [],
            type="array",
            description="Tables to extract (empty = all)",
        ),
    },
    tags=["commercepulse", "backfill"],
    doc_md="""
### CommercePulse Backfill

Extracts a bounded date range from Postgres into bronze, then processes silver.
Idempotent: re-running with the same run_id is safe (ledger deduplication).
""",
) as dag:

    # Build optional --table flags from params
    _table_flags = (
        "{% if params.tables %}"
        "{% for t in params.tables %} --table {{ t }}{% endfor %}"
        "{% endif %}"
    )

    bronze_extract = BashOperator(
        task_id="bronze_extract",
        bash_command=(
            f"{PYTHON} -m ingestion.extractor"
            " --start {{ params.start_date }}"
            " --end {{ params.end_date }}"
            f"{_table_flags}"
        ),
        cwd=CP_HOME,
    )

    silver_job = BashOperator(
        task_id="silver_job",
        bash_command=(
            f"{PYTHON} -m lakehouse.silver_job"
            f"{_table_flags}"
        ),
        cwd=CP_HOME,
    )

    export_snapshot = BashOperator(
        task_id="export_snapshot",
        bash_command=f"{PYTHON} -m lakehouse.export_snapshot",
        cwd=CP_HOME,
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command="dbt build --profiles-dir . --target local",
        cwd=f"{CP_HOME}/warehouse/dbt",
    )

    bronze_extract >> silver_job >> export_snapshot >> dbt_build
