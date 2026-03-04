from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sparkpilot.exceptions import EntityNotFoundError, QuotaExceededError
from sparkpilot.models import Environment, Run
from sparkpilot.services._helpers import ACTIVE_RUN_STATES


def _run_vcpu(resources: dict[str, int]) -> int:
    driver = int(resources.get("driver_vcpu", 0))
    executor = int(resources.get("executor_vcpu", 0))
    count = int(resources.get("executor_instances", 0))
    return driver + (executor * count)


def lock_environment_for_quota(db: Session, environment_id: str) -> Environment:
    env = db.execute(
        select(Environment)
        .where(Environment.id == environment_id)
        .with_for_update()
    ).scalar_one_or_none()
    if env is None:
        raise EntityNotFoundError("Environment not found.")
    return env


def enforce_quota_for_run(db: Session, env: Environment, requested_resources: dict[str, int]) -> None:
    active_count = db.execute(
        select(func.count(Run.id)).where(
            Run.environment_id == env.id,
            Run.state.in_(ACTIVE_RUN_STATES),
        )
    ).scalar_one()
    if active_count >= env.max_concurrent_runs:
        raise QuotaExceededError(
            f"Concurrent run limit reached ({env.max_concurrent_runs})."
        )

    active_runs = db.execute(
        select(Run.requested_resources_json).where(
            Run.environment_id == env.id,
            Run.state.in_(ACTIVE_RUN_STATES),
        )
    ).scalars()
    active_vcpu = sum(_run_vcpu(item or {}) for item in active_runs)
    requested_vcpu = _run_vcpu(requested_resources)
    if active_vcpu + requested_vcpu > env.max_vcpu:
        raise QuotaExceededError(
            f"vCPU quota exceeded ({env.max_vcpu})."
        )
