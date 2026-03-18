"""SparkPilot Airflow integration test DAG.

Validates the full provider surface:
- Regular synchronous submit + wait
- Deferrable trigger path
- Run sensor
- Cancel path

Set the following environment variables before triggering:
    SPARKPILOT_EXAMPLE_JOB_ID   - Job id created by setup_sparkpilot_job.py
"""
from __future__ import annotations

from datetime import datetime
import os

from airflow import DAG
from airflow.operators.python import PythonOperator

from airflow.providers.sparkpilot.operators.sparkpilot import (
    SparkPilotCancelRunOperator,
    SparkPilotSubmitRunOperator,
)
from airflow.providers.sparkpilot.sensors.sparkpilot import SparkPilotRunSensor


JOB_ID = os.environ["SPARKPILOT_EXAMPLE_JOB_ID"]

# ---------------------------------------------------------------------------
# DAG 1: synchronous submit + wait (original integration test)
# ---------------------------------------------------------------------------

with DAG(
    dag_id="sparkpilot_integration_submit_wait",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["sparkpilot", "integration"],
) as dag_submit_wait:
    SparkPilotSubmitRunOperator(
        task_id="submit_and_wait",
        sparkpilot_conn_id="sparkpilot_default",
        job_id=JOB_ID,
        golden_path="small",
        wait_for_completion=True,
        poll_interval_seconds=2,
        timeout_seconds=240,
    )


# ---------------------------------------------------------------------------
# DAG 2: deferrable trigger path
# ---------------------------------------------------------------------------

with DAG(
    dag_id="sparkpilot_integration_deferrable",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["sparkpilot", "integration", "deferrable"],
) as dag_deferrable:
    SparkPilotSubmitRunOperator(
        task_id="submit_deferrable",
        sparkpilot_conn_id="sparkpilot_default",
        job_id=JOB_ID,
        golden_path="small",
        deferrable=True,
        poll_interval_seconds=5,
        timeout_seconds=300,
    )


# ---------------------------------------------------------------------------
# DAG 3: sensor path — submit (no wait) then sensor
# ---------------------------------------------------------------------------

with DAG(
    dag_id="sparkpilot_integration_sensor",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["sparkpilot", "integration", "sensor"],
) as dag_sensor:
    submit_task = SparkPilotSubmitRunOperator(
        task_id="submit_no_wait",
        sparkpilot_conn_id="sparkpilot_default",
        job_id=JOB_ID,
        golden_path="small",
        wait_for_completion=False,
        poll_interval_seconds=2,
        timeout_seconds=30,
    )

    def _get_run_id(**context):  # noqa: ANN003, ANN202
        xcom = context["task_instance"].xcom_pull(task_ids="submit_no_wait")
        if not xcom or not xcom.get("id"):
            raise ValueError("No run id in XCom from submit_no_wait.")
        return xcom["id"]

    get_run_id = PythonOperator(
        task_id="get_run_id",
        python_callable=_get_run_id,
    )

    sensor = SparkPilotRunSensor(
        task_id="wait_for_run",
        sparkpilot_conn_id="sparkpilot_default",
        run_id="{{ task_instance.xcom_pull(task_ids='get_run_id') }}",
        poke_interval=5,
        timeout=300,
    )

    submit_task >> get_run_id >> sensor  # type: ignore[operator]


# ---------------------------------------------------------------------------
# DAG 4: cancel path — submit then immediately cancel
# ---------------------------------------------------------------------------

with DAG(
    dag_id="sparkpilot_integration_cancel",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["sparkpilot", "integration", "cancel"],
) as dag_cancel:
    submit_for_cancel = SparkPilotSubmitRunOperator(
        task_id="submit_for_cancel",
        sparkpilot_conn_id="sparkpilot_default",
        job_id=JOB_ID,
        golden_path="small",
        wait_for_completion=False,
        poll_interval_seconds=2,
        timeout_seconds=30,
    )

    cancel_task = SparkPilotCancelRunOperator(
        task_id="cancel_run",
        sparkpilot_conn_id="sparkpilot_default",
        run_id="{{ task_instance.xcom_pull(task_ids='submit_for_cancel')['id'] }}",
        wait_for_completion=True,
        poll_interval_seconds=5,
        timeout_seconds=120,
    )

    submit_for_cancel >> cancel_task  # type: ignore[operator]
