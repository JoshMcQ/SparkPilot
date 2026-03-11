"""Financial operations: budgets, cost allocation, CUR reconciliation, and usage recording."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import logging
import re
import time
import uuid
from typing import Any

import boto3
from botocore.exceptions import ClientError
from sparkpilot.cost_center import resolve_cost_center_for_environment
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
EC2_MEMORY_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)")
X86_INSTANCE_PAIR_CANDIDATES = [
    ("c6i.xlarge", "r6i.xlarge"),
    ("c7i.xlarge", "r7i.xlarge"),
    ("m6i.xlarge", "r6i.xlarge"),
]
ARM64_INSTANCE_PAIR_CANDIDATES = [
    ("c6g.xlarge", "r6g.xlarge"),
    ("c7g.xlarge", "r7g.xlarge"),
    ("m6g.xlarge", "r6g.xlarge"),
]
PRICING_REFERENCE_VCPU = 4.0
PRICING_REFERENCE_MEMORY_GB = 16.0

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PricingSnapshot:
    vcpu_usd_per_second: float
    memory_gb_usd_per_second: float
    arm64_discount_pct: float
    mixed_discount_pct: float
    source: str


_PRICING_CACHE: dict[str, tuple[float, PricingSnapshot]] = {}
ATHENA_RESULT_PAGE_SIZE = 1000


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
# Live pricing helpers (AWS Pricing API + fallback cache)
# ---------------------------------------------------------------------------

def _reset_pricing_cache() -> None:
    _PRICING_CACHE.clear()


def _clamp_discount(value: float) -> float:
    return max(0.0, min(100.0, value))


def _static_pricing_snapshot(settings: Any, *, source: str = "static") -> PricingSnapshot:
    return PricingSnapshot(
        vcpu_usd_per_second=settings.pricing_vcpu_usd_per_second,
        memory_gb_usd_per_second=settings.pricing_memory_gb_usd_per_second,
        arm64_discount_pct=settings.pricing_arm64_discount_pct,
        mixed_discount_pct=settings.pricing_mixed_discount_pct,
        source=source,
    )


def _extract_hourly_price_usd(price_item: dict[str, Any]) -> float:
    terms = price_item.get("terms", {}).get("OnDemand", {})
    prices: list[float] = []
    for term in terms.values():
        for dimension in term.get("priceDimensions", {}).values():
            unit = str(dimension.get("unit", "")).strip().lower()
            if "hr" not in unit:
                continue
            raw_usd = str(dimension.get("pricePerUnit", {}).get("USD", "")).strip()
            if not raw_usd:
                continue
            try:
                value = float(raw_usd)
            except ValueError:
                continue
            if value > 0:
                prices.append(value)
    if not prices:
        raise ValueError("No on-demand hourly USD pricing dimensions found.")
    return min(prices)


def _parse_memory_gb(raw_memory: str) -> float:
    normalized = raw_memory.replace(",", "")
    match = EC2_MEMORY_RE.search(normalized)
    if not match:
        raise ValueError(f"Unable to parse instance memory from {raw_memory!r}.")
    return float(match.group(1))


def _extract_ec2_sample(
    pricing_client: Any,
    *,
    region: str,
    instance_type: str,
) -> tuple[float, float, float]:
    paginator = pricing_client.get_paginator("get_products")
    filters = [
        {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
        {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
        {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
        {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
        {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
    ]
    pages = paginator.paginate(ServiceCode="AmazonEC2", Filters=filters, FormatVersion="aws_v1")
    for page in pages:
        for raw in page.get("PriceList", []):
            item = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(item, dict):
                continue
            attributes = item.get("product", {}).get("attributes", {})
            if attributes.get("instanceType") != instance_type:
                continue
            region_code = str(attributes.get("regionCode", "")).strip()
            if region_code != region:
                continue
            try:
                price_per_hour = _extract_hourly_price_usd(item)
                vcpu = float(str(attributes.get("vcpu", "0")).strip())
                memory_gb = _parse_memory_gb(str(attributes.get("memory", "")).strip())
            except ValueError:
                continue
            if vcpu <= 0 or memory_gb <= 0:
                continue
            return price_per_hour, vcpu, memory_gb
    raise ValueError(
        f"Unable to find on-demand Linux shared pricing sample for {instance_type} in region {region}."
    )


def _solve_linear_rates(
    sample_a: tuple[float, float, float],
    sample_b: tuple[float, float, float],
) -> tuple[float, float]:
    price_a, vcpu_a, memory_a = sample_a
    price_b, vcpu_b, memory_b = sample_b
    denominator = (vcpu_a * memory_b) - (vcpu_b * memory_a)
    if abs(denominator) < 1e-9:
        raise ValueError("Unable to derive per-resource rates from degenerate instance samples.")
    vcpu_usd_per_hour = ((price_a * memory_b) - (price_b * memory_a)) / denominator
    memory_usd_per_hour = ((price_b * vcpu_a) - (price_a * vcpu_b)) / denominator
    if vcpu_usd_per_hour <= 0 or memory_usd_per_hour <= 0:
        raise ValueError("Derived non-positive per-resource rates from AWS pricing samples.")
    return vcpu_usd_per_hour, memory_usd_per_hour


def _derive_architecture_rates(
    pricing_client: Any,
    *,
    region: str,
    candidates: list[tuple[str, str]],
) -> tuple[float, float, tuple[str, str]]:
    errors: list[str] = []
    for left, right in candidates:
        try:
            sample_left = _extract_ec2_sample(pricing_client, region=region, instance_type=left)
            sample_right = _extract_ec2_sample(pricing_client, region=region, instance_type=right)
            rates = _solve_linear_rates(sample_left, sample_right)
            return rates[0], rates[1], (left, right)
        except ValueError as exc:
            errors.append(str(exc))
            continue
    raise ValueError(
        "Unable to derive pricing rates from AWS Pricing API samples: " + "; ".join(errors[-3:])
    )


def _fetch_pricing_api_snapshot(settings: Any) -> PricingSnapshot:
    pricing_client = boto3.client("pricing", region_name="us-east-1")
    x86_vcpu_hour, x86_memory_hour, x86_pair = _derive_architecture_rates(
        pricing_client,
        region=settings.aws_region,
        candidates=X86_INSTANCE_PAIR_CANDIDATES,
    )
    arm_vcpu_hour, arm_memory_hour, arm_pair = _derive_architecture_rates(
        pricing_client,
        region=settings.aws_region,
        candidates=ARM64_INSTANCE_PAIR_CANDIDATES,
    )
    x86_reference_hour = (
        x86_vcpu_hour * PRICING_REFERENCE_VCPU
        + x86_memory_hour * PRICING_REFERENCE_MEMORY_GB
    )
    arm_reference_hour = (
        arm_vcpu_hour * PRICING_REFERENCE_VCPU
        + arm_memory_hour * PRICING_REFERENCE_MEMORY_GB
    )
    if x86_reference_hour <= 0:
        raise ValueError("Unable to derive reference x86 hourly price from AWS Pricing API.")
    arm64_discount_pct = _clamp_discount((1.0 - (arm_reference_hour / x86_reference_hour)) * 100.0)
    mixed_discount_pct = _clamp_discount(arm64_discount_pct / 2.0)
    return PricingSnapshot(
        vcpu_usd_per_second=x86_vcpu_hour / 3600.0,
        memory_gb_usd_per_second=x86_memory_hour / 3600.0,
        arm64_discount_pct=arm64_discount_pct,
        mixed_discount_pct=mixed_discount_pct,
        source=(
            f"aws_pricing_api:x86={x86_pair[0]}+{x86_pair[1]}:"
            f"arm={arm_pair[0]}+{arm_pair[1]}"
        ),
    )


def _resolve_runtime_pricing(settings: Any) -> PricingSnapshot:
    cache_key = f"{settings.pricing_source}:{settings.aws_region}"
    now_epoch = time.time()
    cached = _PRICING_CACHE.get(cache_key)
    if cached and cached[0] > now_epoch:
        return cached[1]

    if settings.pricing_source == "static":
        snapshot = _static_pricing_snapshot(settings)
    elif settings.pricing_source == "auto" and settings.dry_run_mode:
        snapshot = _static_pricing_snapshot(settings)
    else:
        try:
            snapshot = _fetch_pricing_api_snapshot(settings)
        except (ValueError, ClientError) as exc:
            if settings.pricing_source == "aws_pricing_api":
                raise
            logger.warning(
                "AWS pricing API lookup failed in auto mode; falling back to static pricing.",
                exc_info=exc,
            )
            snapshot = _static_pricing_snapshot(settings, source="static-fallback")

    _PRICING_CACHE[cache_key] = (now_epoch + settings.pricing_cache_seconds, snapshot)
    return snapshot


def resolve_runtime_pricing(settings: Any | None = None) -> PricingSnapshot:
    runtime_settings = settings or get_settings()
    return _resolve_runtime_pricing(runtime_settings)


# ---------------------------------------------------------------------------
# Billing / cost helpers
# ---------------------------------------------------------------------------

def _billing_period(value: datetime | None = None) -> str:
    dt = value or _now()
    return f"{dt.year:04d}-{dt.month:02d}"


def _team_key_for_environment(env: Environment) -> str:
    return env.tenant_id


def _cost_center_for_environment(env: Environment, settings: Any) -> str:
    return resolve_cost_center_for_environment(settings=settings, environment=env)


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

def get_cost_showback(
    db: Session,
    *,
    team: str,
    period: str,
    limit: int = 200,
    offset: int = 0,
) -> CostShowbackResponse:
    filters = and_(
        CostAllocation.team == team,
        CostAllocation.billing_period == period,
    )
    total_estimated, total_actual, total_effective = db.execute(
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
        ).where(filters)
    ).one()
    rows = list(
        db.execute(
            select(CostAllocation)
            .where(filters)
            .order_by(CostAllocation.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    items: list[dict[str, Any]] = []
    for item in rows:
        estimated = int(item.estimated_cost_usd_micros or 0)
        actual = int(item.actual_cost_usd_micros) if item.actual_cost_usd_micros is not None else None
        effective = actual if actual is not None else estimated
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
        total_estimated_cost_usd_micros=int(total_estimated),
        total_actual_cost_usd_micros=int(total_actual),
        total_effective_cost_usd_micros=int(total_effective),
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
    for row in rows:
        values = row.get("Data", [])
        if len(values) < 2:
            continue
        run_id = str(values[0].get("VarCharValue") or "").strip()
        cost_value = str(values[1].get("VarCharValue") or "").strip()
        if not run_id or cost_value is None:
            continue
        if run_id.lower() == "run_id" and cost_value.lower() == "cost_usd":
            continue
        try:
            micros = int((Decimal(cost_value) * Decimal("1000000")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, ValueError):
            continue
        cost_by_run_id[run_id] = int(cost_by_run_id.get(run_id, 0) + micros)
    return cost_by_run_id


def _collect_athena_result_rows(
    *,
    athena: Any,
    query_execution_id: str,
    page_size: int = ATHENA_RESULT_PAGE_SIZE,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    next_token: str | None = None
    while True:
        request: dict[str, Any] = {
            "QueryExecutionId": query_execution_id,
            "MaxResults": page_size,
        }
        if next_token:
            request["NextToken"] = next_token
        result = athena.get_query_results(**request)
        rows.extend(result.get("ResultSet", {}).get("Rows", []))
        next_token = result.get("NextToken")
        if not next_token:
            break
    return rows


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

    rows = _collect_athena_result_rows(
        athena=athena,
        query_execution_id=query_execution_id,
    )
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
    settings = get_settings()
    duration_seconds = 0
    if run.started_at and run.ended_at:
        duration_seconds = max(0, int((_as_utc(run.ended_at) - _as_utc(run.started_at)).total_seconds()))
    resources = RequestedResources(**(run.requested_resources_json or {}))
    pricing = _resolve_runtime_pricing(settings)
    vcpu_seconds = duration_seconds * resources.total_vcpu()
    memory_total = resources.driver_memory_gb + (resources.executor_memory_gb * resources.executor_instances)
    memory_gb_seconds = duration_seconds * memory_total
    architecture_multiplier = 1.0
    if env.instance_architecture == "arm64":
        architecture_multiplier = max(0.0, 1.0 - (pricing.arm64_discount_pct / 100.0))
    elif env.instance_architecture == "mixed":
        architecture_multiplier = max(0.0, 1.0 - (pricing.mixed_discount_pct / 100.0))
    estimated_cost_usd = (
        (vcpu_seconds * pricing.vcpu_usd_per_second) +
        (memory_gb_seconds * pricing.memory_gb_usd_per_second)
    ) * architecture_multiplier
    estimated_cost_usd_micros = int(estimated_cost_usd * 1_000_000)
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
                cost_center=_cost_center_for_environment(env, settings=settings),
                billing_period=_billing_period(run.ended_at or _now()),
                estimated_vcpu_seconds=vcpu_seconds,
                estimated_memory_gb_seconds=memory_gb_seconds,
                estimated_cost_usd_micros=estimated_cost_usd_micros,
            )
        )
