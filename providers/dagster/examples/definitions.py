from __future__ import annotations

from dagster_sparkpilot._compat import Definitions, job
from dagster_sparkpilot.assets import sparkpilot_run_lifecycle_asset
from dagster_sparkpilot.ops import (
    sparkpilot_cancel_run_op,
    sparkpilot_submit_run_op,
    sparkpilot_wait_for_run_op,
)
from dagster_sparkpilot.resource import sparkpilot_resource


@job(resource_defs={"sparkpilot": sparkpilot_resource})
def sparkpilot_submit_wait_job():
    sparkpilot_wait_for_run_op(sparkpilot_submit_run_op())


@job(resource_defs={"sparkpilot": sparkpilot_resource})
def sparkpilot_submit_cancel_job():
    sparkpilot_cancel_run_op(sparkpilot_submit_run_op())


defs = Definitions(
    jobs=[sparkpilot_submit_wait_job, sparkpilot_submit_cancel_job],
    assets=[sparkpilot_run_lifecycle_asset],
    resources={"sparkpilot": sparkpilot_resource},
)

