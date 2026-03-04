from __future__ import annotations

from datetime import datetime
import os

from airflow import DAG
from airflow.providers.sparkpilot.operators.sparkpilot import SparkPilotSubmitRunOperator
from airflow.providers.sparkpilot.sensors.sparkpilot import SparkPilotRunSensor


JOB_ID = os.getenv("SPARKPILOT_EXAMPLE_JOB_ID", "")


with DAG(
    dag_id="example_sparkpilot_dag",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["sparkpilot"],
) as dag:
    submit_and_wait = SparkPilotSubmitRunOperator(
        task_id="submit_and_wait",
        sparkpilot_conn_id="sparkpilot_default",
        job_id=JOB_ID,
        golden_path="small",
        wait_for_completion=False,
    )

    wait_terminal = SparkPilotRunSensor(
        task_id="wait_terminal",
        sparkpilot_conn_id="sparkpilot_default",
        run_id=submit_and_wait.output["id"],
        poke_interval=15,
        timeout=3600,
    )

    submit_and_wait >> wait_terminal
