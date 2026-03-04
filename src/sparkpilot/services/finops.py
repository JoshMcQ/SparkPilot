"""Financial operations: budgets, cost allocation, CUR reconciliation, and usage recording."""

from datetime import datetime
import re
import time
import uuid
from typing import Any

import boto3
from sparkpilot.exceptions import EntityNotFoundError, ValidationError
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from sparkpilot.audit import write_audit_event
from sparkpilot.config import get_settings
from sparkpilot.models import (
    CostAllocation,
    Environment,
    Run,
    TeamBudget,
    UsageRecord,
)
from sparkpilot.schemas import (
    CostShowbackResponse,
    RequestedResources,
    TeamBudgetCreateRequest,
)
from sparkpilot.services._helpers import _as_utc, _now


# ---------------------------------------------------------------------------
# Athena SQL safety helpers
# ---------------------------------------------------------------------------

ATHENA_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_athena_identifier(value: str, setting_name: str) -> str:
    candidate = value.strip()
    if not candidate or not ATHENA_IDENTIFIER_RE.match(candidate):
        raise ValueError(
            f"Invalid Athena identifier for {setting_name}: {value!r}. "
            "Use alphanumeric/underscore identifiers only."
        )
    return candidate


def _validate_uuid_run_ids(run_ids: list[str]) -> list[str]:
    invalid: list[str] = []
    valid: list[str] = []
    for run_id in run_ids:
        try:
            uuid.UUID(run_id)
        except ValueError:
            invalid.append(run_id)
            continue
        valid.append(run_id)
    if invalid:
        sample = ", ".join(invalid[:3])
        raise ValueError(
            f"Invalid run_id values for CUR reconciliation (expected UUID format): {sample}."
        )
    return valid


def _quote_athena_literal(value: str) -> str:
    # Athena does not support parameterized SQL for this API. Escape defensively.
    return "'" + value.replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Billing / cost helpers
# ---------------------------------------------------------------------------

def _billing_period(value: datetime | None = None) -> str:
    dt = value or _now()
    return f"{dt.year:04d}-{dt.month:02d}"


def _team_key_for_environment(env: Environment) -> str:
    return env.tenant_id


def _cost_center_for_environment(env: Environment) -> str:
    if env.eks_namespace:
        return env.eks_namespace
    if env.emr_virtual_cluster_id:
        return env.emr_virtual_cluster_id
    return env.id


def _team_spend_for_period(db: Session, team: str, period: str) -> tuple[int, int, int]:
    # Aggregate query without GROUP BY always returns exactly one row; `.one()` is safe.
    estimated, actual, effective = db.execute(
        select(
            func.coalesce(func.sum(CostAllocation.estimated_cost_usd_micros), 0),
            func.coalesce(
                func.sum(
                    case(
                        (CostAllocation.actual_cost_usd_micros.is_not(None), CostAllocation.actual_cost_usd_micros),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (CostAllocation.actual_cost_usd_micros.is_not(None), CostAllocation.actual_cost_usd_micros),
                        else_=CostAllocation.estimated_cost_usd_micros,
                    )
                ),
                0,
            ),
        ).where(
            and_(
                CostAllocation.team == team,
                CostAllocation.billing_period == period,
            )
        )
    ).one()
    return int(estimated), int(actual), int(effective)


# ---------------------------------------------------------------------------
# Team budget CRUD
# ---------------------------------------------------------------------------

def create_or_update_team_budget(db: Session, req: TeamBudgetCreateRequest) -> TeamBudget:
    if req.warn_threshold_pct > req.block_threshold_pct:
        raise ValidationError("warn_threshold_pct must be less than or equal to block_threshold_pct.")
    item = db.execute(select(TeamBudget).where(TeamBudget.team == req.team)).scalar_one_or_none()
    if item is None:
        item = TeamBudget(team=req.team)
        db.add(item)
    item.monthly_budget_usd_micros = req.monthly_budget_usd_micros
    item.warn_threshold_pct = req.warn_threshold_pct
    item.block_threshold_pct = req.block_threshold_pct
    db.commit()
    db.refresh(item)
    return item


def get_team_budget(db: Session, team: str) -> TeamBudget:
    item = db.execute(select(TeamBudget).where(TeamBudget.team == team)).scalar_one_or_none()
    if item is None:
        raise EntityNotFoundError("Team budget not found.")
    return item


# ---------------------------------------------------------------------------
# Cost showback
# ---------------------------------------------------------------------------

def get_cost_showback(db: Session, *, team: str, period: str) -> CostShowbackResponse:
    rows = list(
        db.execute(
            select(CostAllocation).where(
                and_(
                    CostAllocation.team == team,
                    CostAllocation.billing_period == period,
                )
            )
        ).scalars()
    )
    items: list[dict[str, Any]] = []
    total_estimated = 0
    total_actual = 0
    total_effective = 0
    for item in rows:
        estimated = int(item.estimated_cost_usd_micros or 0)
        actual = int(item.actual_cost_usd_micros) if item.actual_cost_usd_micros is not None else None
        effective = actual if actual is not None else estimated
        total_estimated += estimated
        total_actual += actual or 0
        total_effective += effective
        items.append(
            {
                "run_id": item.run_id,
                "environment_id": item.environment_id,
                "team": item.team,
                "cost_center": item.cost_center,
                "estimated_cost_usd_micros": estimated,
                "actual_cost_usd_micros": actual,
                "effective_cost_usd_micros": effective,
                "billing_period": item.billing_period,
                "cur_reconciled_at": item.cur_reconciled_at,
            }
        )
    return CostShowbackResponse(
        team=team,
        period=period,
        total_estimated_cost_usd_micros=total_estimated,
        total_actual_cost_usd_micros=total_actual,
        total_effective_cost_usd_micros=total_effective,
        items=items,
    )


# ---------------------------------------------------------------------------
# CUR reconciliation
# ---------------------------------------------------------------------------

def _cur_reconciliation_configured(settings: Any) -> bool:
    return bool(
        settings.cur_athena_database.strip()
        and settings.cur_athena_table.strip()
        and settings.cur_athena_output_location.strip()
    )


def _load_pending_cost_allocations(db: Session, *, limit: int) -> list[CostAllocation]:
    return list(
        db.execute(
            select(CostAllocation)
            .where(CostAllocation.actual_cost_usd_micros.is_(None))
            .order_by(CostAllocation.created_at.asc())
            .limit(limit)
        ).scalars()
    )


def _build_cur_reconciliation_query(
    *,
    settings: Any,
    pending: list[CostAllocation],
) -> tuple[str, str, str]:
    run_id_column = _validate_athena_identifier(settings.cur_run_id_column, "cur_run_id_column")
    cost_column = _validate_athena_identifier(settings.cur_cost_column, "cur_cost_column")
    athena_database = _validate_athena_identifier(settings.cur_athena_database, "cur_athena_database")
    athena_table = _validate_athena_identifier(settings.cur_athena_table, "cur_athena_table")

    run_ids = _validate_uuid_run_ids(sorted({item.run_id for item in pending}))
    if not run_ids:
        return "", athena_database, athena_table

    quoted_ids = ", ".join(_quote_athena_literal(item) for item in run_ids)
    sql = (
        f"SELECT {run_id_column} AS run_id, "
        f"SUM(CAST({cost_column} AS DOUBLE)) AS cost_usd "
        f"FROM {athena_database}.{athena_table} "
        f"WHERE {run_id_column} IN ({quoted_ids}) "
        "GROUP BY 1"
    )
    return sql, athena_database, athena_table


def _wait_for_athena_query(
    *,
    athena: Any,
    query_execution_id: str,
    timeout_seconds: int,
    poll_seconds: int,
) -> None:
    deadline = time.time() + timeout_seconds
    state = "QUEUED"
    while time.time() < deadline:
        execution = athena.get_query_execution(QueryExecutionId=query_execution_id)
        state = execution["QueryExecution"]["Status"]["State"]
        if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            break
        time.sleep(max(1, poll_seconds))
    if state != "SUCCEEDED":
        raise ValueError(f"CUR Athena reconciliation query failed with state={state}.")


def _parse_athena_cost_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    cost_by_run_id: dict[str, int] = {}
    for row in rows[1:]:
        values = row.get("Data", [])
        if len(values) < 2:
            continue
        run_id = values[0].get("VarCharValue")
        cost_value = values[1].get("VarCharValue")
        if not run_id or cost_value is None:
            continue
        try:
            micros = int(float(cost_value) * 1_000_000)
        except ValueError:
            continue
        cost_by_run_id[run_id] = micros
    return cost_by_run_id


def _apply_cur_cost_updates(
    *,
    pending: list[CostAllocation],
    cost_by_run_id: dict[str, int],
) -> int:
    changed = 0
    reconciled_at = _now()
    for item in pending:
        if item.run_id not in cost_by_run_id:
            continue
        item.actual_cost_usd_micros = cost_by_run_id[item.run_id]
        item.cur_reconciled_at = reconciled_at
        changed += 1
    return changed


def process_cur_reconciliation_once(db: Session, *, actor: str = "worker:cur-reconciliation", limit: int = 200) -> int:
    settings = get_settings()
    if not _cur_reconciliation_configured(settings):
        return 0

    pending = _load_pending_cost_allocations(db, limit=limit)
    if not pending:
        return 0

    sql, athena_database, athena_table = _build_cur_reconciliation_query(
        settings=settings,
        pending=pending,
    )
    if not sql:
        return 0

    athena = boto3.client("athena", region_name=settings.aws_region)
    start = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": athena_database},
        ResultConfiguration={"OutputLocation": settings.cur_athena_output_location},
        WorkGroup=settings.cur_athena_workgroup,
    )
    query_execution_id = start["QueryExecutionId"]
    _wait_for_athena_query(
        athena=athena,
        query_execution_id=query_execution_id,
        timeout_seconds=settings.cur_query_timeout_seconds,
        poll_seconds=settings.cur_poll_seconds,
    )

    results = athena.get_query_results(QueryExecutionId=query_execution_id)
    rows = results.get("ResultSet", {}).get("Rows", [])
    cost_by_run_id = _parse_athena_cost_rows(rows)
    changed = _apply_cur_cost_updates(pending=pending, cost_by_run_id=cost_by_run_id)

    if changed:
        write_audit_event(
            db,
            actor=actor,
            action="cost.cur_reconciliation",
            entity_type="system",
            entity_id="cost_allocations",
            details={
                "changed": changed,
                "query_execution_id": query_execution_id,
                "database": athena_database,
                "table": athena_table,
            },
        )
        db.commit()
    return changed


# ---------------------------------------------------------------------------
# Usage / cost allocation recording
# ---------------------------------------------------------------------------

def _record_usage_if_needed(db: Session, run: Run, env: Environment) -> None:
    existing = db.execute(select(UsageRecord).where(UsageRecord.run_id == run.id)).scalar_one_or_none()
    if existing:
        return
    duration_seconds = 0
    if run.started_at and run.ended_at:
        duration_seconds = max(0, int((_as_utc(run.ended_at) - _as_utc(run.started_at)).total_seconds()))
    resources = RequestedResources(**(run.requested_resources_json or {}))
    vcpu_seconds = duration_seconds * resources.total_vcpu()
    memory_total = resources.driver_memory_gb + (resources.executor_memory_gb * resources.executor_instances)
    memory_gb_seconds = duration_seconds * memory_total
    # Placeholder pricing model in micros (1 USD = 1_000_000 micros).
    architecture_multiplier = 1.0
    if env.instance_architecture == "arm64":
        architecture_multiplier = 0.8
    elif env.instance_architecture == "mixed":
        architecture_multiplier = 0.9
    estimated_cost_usd_micros = int(((vcpu_seconds * 35) + (memory_gb_seconds * 4)) * architecture_multiplier)
    db.add(
        UsageRecord(
            tenant_id=env.tenant_id,
            run_id=run.id,
            vcpu_seconds=vcpu_seconds,
            memory_gb_seconds=memory_gb_seconds,
            estimated_cost_usd_micros=estimated_cost_usd_micros,
        )
    )
    existing_allocation = db.execute(
        select(CostAllocation).where(CostAllocation.run_id == run.id)
    ).scalar_one_or_none()
    if existing_allocation is None:
        db.add(
            CostAllocation(
                run_id=run.id,
                environment_id=env.id,
                tenant_id=env.tenant_id,
                team=_team_key_for_environment(env),
                cost_center=_cost_center_for_environment(env),
                billing_period=_billing_period(run.ended_at or _now()),
                estimated_vcpu_seconds=vcpu_seconds,
                estimated_memory_gb_seconds=memory_gb_seconds,
                estimated_cost_usd_micros=estimated_cost_usd_micros,
            )
        )
