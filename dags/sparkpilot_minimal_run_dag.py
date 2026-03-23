"""SparkPilot minimal-resource run DAG — Issue #36 evidence.

Submits a SparkPi job with minimal CPU/memory overrides to fit within
2×t3.large EKS nodes (4 vCPU total, ~14 GB usable).

Spark conf overrides:
  spark.driver.cores=1
  spark.driver.memory=1g
  spark.executor.instances=1
  spark.executor.cores=1
  spark.executor.memory=2g

These are passed via spark_conf in the RunCreateRequest body, which maps
to spark_conf_overrides_json → sparkSubmitParameters in the EMR start_job_run call.

Triggered manually: airflow dags trigger sparkpilot_minimal_run
"""
from __future__ import annotations

import os
from datetime import datetime

from airflow import DAG
from airflow.providers.sparkpilot.operators.sparkpilot import SparkPilotSubmitRunOperator
from airflow.providers.sparkpilot.sensors.sparkpilot import SparkPilotRunSensor


JOB_ID = os.getenv("SPARKPILOT_EXAMPLE_JOB_ID", "")

MINIMAL_SPARK_CONF = {
    "spark.driver.cores": "1",
    "spark.driver.memory": "1g",
    "spark.executor.instances": "1",
    "spark.executor.cores": "1",
    "spark.executor.memory": "2g",
    # Kubernetes millicores request — allows fractional CPU scheduling on t3.large nodes
    "spark.kubernetes.driver.request.cores": "500m",
    "spark.kubernetes.executor.request.cores": "500m",
}

MINIMAL_RESOURCES = {
    "driver_vcpu": 1,
    "driver_memory_gb": 1,
    "executor_vcpu": 1,
    "executor_memory_gb": 2,
    "executor_instances": 1,
}


with DAG(
    dag_id="sparkpilot_minimal_run",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["sparkpilot", "evidence", "issue-36"],
    doc_md=__doc__,
) as dag:
    submit = SparkPilotSubmitRunOperator(
        task_id="submit_minimal_run",
        sparkpilot_conn_id="sparkpilot_default",
        job_id=JOB_ID,
        spark_conf=MINIMAL_SPARK_CONF,
        requested_resources=MINIMAL_RESOURCES,
        wait_for_completion=False,
    )

    wait = SparkPilotRunSensor(
        task_id="wait_for_completion",
        sparkpilot_conn_id="sparkpilot_default",
        run_id=submit.output["id"],
        poke_interval=30,
        timeout=1800,
    )

    submit >> wait
