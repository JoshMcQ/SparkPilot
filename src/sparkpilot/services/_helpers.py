"""Shared constants, entity lookups, and small helpers."""

from datetime import UTC, datetime
import logging
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from sparkpilot.exceptions import EntityNotFoundError
from sparkpilot.models import (
    Environment,
    Job,
    Run,
    Team,
    Tenant,
)
from sparkpilot.time_utils import _as_utc  # noqa: F401 — re-exported; callers import _as_utc from here

logger = logging.getLogger(__name__)
EntityT = TypeVar("EntityT")

# ---------------------------------------------------------------------------
# Constants shared across sub-modules
# ---------------------------------------------------------------------------

TERMINAL_RUN_STATES = {"succeeded", "failed", "cancelled", "timed_out"}
ACTIVE_RUN_STATES = {"queued", "dispatching", "accepted", "running"}

FORBIDDEN_SPARK_CONF_PREFIXES = (
    "spark.kubernetes.authenticate.",
    "spark.kubernetes.driver.serviceAccountName",
    "spark.kubernetes.executor.serviceAccountName",
)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Generic entity lookups
# ---------------------------------------------------------------------------

def _require_entity(
    db: Session,
    model: type[EntityT],
    entity_id: str,
    *,
    detail: str,
) -> EntityT:
    entity = db.get(model, entity_id)
    if entity is None:
        raise EntityNotFoundError(detail)
    return entity


def _require_tenant(db: Session, tenant_id: str) -> Tenant:
    return _require_entity(db, Tenant, tenant_id, detail="Tenant not found.")


def _require_team(db: Session, team_id: str) -> Team:
    return _require_entity(db, Team, team_id, detail="Team not found.")


def _require_environment(db: Session, environment_id: str) -> Environment:
    return _require_entity(db, Environment, environment_id, detail="Environment not found.")


def _require_job(db: Session, job_id: str) -> Job:
    return _require_entity(db, Job, job_id, detail="Job not found.")


def _require_run(db: Session, run_id: str) -> Run:
    return _require_entity(db, Run, run_id, detail="Run not found.")


# ---------------------------------------------------------------------------
# Spark configuration policy
# ---------------------------------------------------------------------------

def _validate_custom_spark_conf_policy(spark_conf: dict[str, str] | None) -> list[str]:
    if not spark_conf:
        return []
    violations: list[str] = []
    for key in spark_conf.keys():
        key_text = str(key)
        if any(key_text.startswith(prefix) for prefix in FORBIDDEN_SPARK_CONF_PREFIXES):
            violations.append(key_text)
    return sorted(set(violations))


# ---------------------------------------------------------------------------
# Model serialisation
# ---------------------------------------------------------------------------

def model_to_dict(model: Any, *, include: set[str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for column in model.__table__.columns:
        if include and column.name not in include:
            continue
        payload[column.name] = getattr(model, column.name)
    return payload
