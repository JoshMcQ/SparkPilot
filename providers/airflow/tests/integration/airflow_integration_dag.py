from __future__ import annotations

from datetime import datetime
import os

from airflow import DAG
from airflow.providers.sparkpilot.operators.sparkpilot import SparkPilotSubmitRunOperator


JOB_ID = os.environ["SPARKPILOT_EXAMPLE_JOB_ID"]


with DAG(
    dag_id="airflow_integration_dag",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
) as dag:
    SparkPilotSubmitRunOperator(
        task_id="submit_and_wait",
        sparkpilot_conn_id="sparkpilot_default",
        job_id=JOB_ID,
        golden_path="small",
        wait_for_completion=True,
        poll_interval_seconds=2,
        timeout_seconds=240,
    )

