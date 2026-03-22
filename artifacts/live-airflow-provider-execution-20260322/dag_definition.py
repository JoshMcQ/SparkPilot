"""
SparkPilot Airflow Provider Evidence DAG — Issue #36
Date: 2026-03-22

This DAG was executed directly via SparkPilotSubmitRunOperator.execute()
against the live SparkPilot API (http://localhost:8000) using mock Airflow
connection objects. No running Airflow scheduler was available locally.

The SparkPilot provider package (apache-airflow-providers-sparkpilot 0.1.0)
is installable and functional; it requires a running Airflow scheduler
for full DAG execution evidence.
"""
from airflow import DAG
from datetime import datetime
from airflow.providers.sparkpilot.operators.sparkpilot import SparkPilotSubmitRunOperator

with DAG(
    dag_id="sparkpilot_live_evidence_20260322",
    start_date=datetime(2026, 3, 22),
    schedule=None,
    catchup=False,
    tags=["sparkpilot", "evidence", "issue-36"],
) as dag:
    submit_job = SparkPilotSubmitRunOperator(
        task_id="sparkpilot_airflow_evidence_20260322",
        job_id="dd87754d-bbef-45fb-bf84-e6686c4b990e",
        sparkpilot_conn_id="sparkpilot_default",
        requested_resources={
            "driver_vcpu": 1,
            "driver_memory_gb": 2,
            "executor_vcpu": 1,
            "executor_memory_gb": 2,
            "executor_instances": 1,
        },
        wait_for_completion=True,
        poll_interval_seconds=15,
        wait_timeout_seconds=1800,
        idempotency_key="airflow-evidence-run-20260322a",
    )
