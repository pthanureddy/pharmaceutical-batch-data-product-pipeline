from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_ID = os.getenv("GCP_PROJECT", "portfolio-project")
REGION = os.getenv("GCP_REGION", "europe-north1")
JOB_NAME = os.getenv("CLOUD_RUN_JOB", "portfolio-pharma-ingest")
SQL_ROOT = os.getenv("PIPELINE_SQL_ROOT", "/home/airflow/gcs/dags/sql/bigquery")


with DAG(
    dag_id="pharmaceutical_batch_data_product",
    description="Run the landing job, merge curated state, and enforce data-quality controls.",
    start_date=datetime(2026, 1, 1),
    schedule="*/15 * * * *",
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "data-platform",
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(minutes=20),
    },
    tags=["data-product", "gcp", "quality"],
) as dag:
    execute_ingest_job = BashOperator(
        task_id="execute_ingest_job",
        bash_command=(
            'gcloud run jobs execute "$CLOUD_RUN_JOB" '
            '--project "$GCP_PROJECT" --region "$GCP_REGION" --wait'
        ),
        env={
            "GCP_PROJECT": PROJECT_ID,
            "GCP_REGION": REGION,
            "CLOUD_RUN_JOB": JOB_NAME,
        },
        append_env=True,
    )

    merge_batch_snapshot = BashOperator(
        task_id="merge_batch_snapshot",
        bash_command=(
            'bq query --project_id="$GCP_PROJECT" --use_legacy_sql=false '
            '< "$PIPELINE_SQL_ROOT/002_incremental_batch_snapshot.sql"'
        ),
        env={"GCP_PROJECT": PROJECT_ID, "PIPELINE_SQL_ROOT": SQL_ROOT},
        append_env=True,
    )

    check_data_quality = BashOperator(
        task_id="check_data_quality",
        bash_command=(
            'bq query --project_id="$GCP_PROJECT" --use_legacy_sql=false '
            '< "$PIPELINE_SQL_ROOT/003_quality_checks.sql"'
        ),
        env={"GCP_PROJECT": PROJECT_ID, "PIPELINE_SQL_ROOT": SQL_ROOT},
        append_env=True,
    )

    execute_ingest_job >> merge_batch_snapshot >> check_data_quality
