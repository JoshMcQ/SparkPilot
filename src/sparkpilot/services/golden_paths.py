"""Golden path template management and seeding."""

from typing import Any

from sparkpilot.exceptions import ConflictError, EntityNotFoundError, ValidationError
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sparkpilot.models import Environment, GoldenPath
from sparkpilot.schemas import GoldenPathCreate
from sparkpilot.services._helpers import _require_environment


# ---------------------------------------------------------------------------
# Default golden path specifications
# ---------------------------------------------------------------------------

def _default_golden_path_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": "small",
            "description": "Small Spark job profile (2 vCPU, 8GB total).",
            "spark_conf_json": {
                "spark.kubernetes.executor.node.selector.eks.amazonaws.com/capacityType": "SPOT",
                "spark.kubernetes.executor.tolerations": "spot=true:NoSchedule",
            },
            "requested_resources_json": {
                "driver_vcpu": 1,
                "driver_memory_gb": 2,
                "executor_vcpu": 1,
                "executor_memory_gb": 6,
                "executor_instances": 1,
            },
            "instance_architecture": "mixed",
            "capacity_type": "spot",
            "max_runtime_minutes": 120,
            "tags_json": {"sparkpilot.default": "true", "size": "small"},
            "recommended_instance_types_json": ["m7g.large", "m7i.large", "r7g.large"],
        },
        {
            "name": "medium",
            "description": "Medium Spark job profile (8 vCPU, 32GB total).",
            "spark_conf_json": {
                "spark.kubernetes.executor.node.selector.eks.amazonaws.com/capacityType": "SPOT",
                "spark.kubernetes.executor.tolerations": "spot=true:NoSchedule",
            },
            "requested_resources_json": {
                "driver_vcpu": 2,
                "driver_memory_gb": 4,
                "executor_vcpu": 2,
                "executor_memory_gb": 7,
                "executor_instances": 3,
            },
            "instance_architecture": "mixed",
            "capacity_type": "spot",
            "max_runtime_minutes": 180,
            "tags_json": {"sparkpilot.default": "true", "size": "medium"},
            "recommended_instance_types_json": ["m7g.xlarge", "m7i.xlarge", "r7g.xlarge"],
        },
        {
            "name": "large",
            "description": "Large Spark job profile (32 vCPU, 128GB total).",
            "spark_conf_json": {
                "spark.kubernetes.executor.node.selector.eks.amazonaws.com/capacityType": "SPOT",
                "spark.kubernetes.executor.tolerations": "spot=true:NoSchedule",
            },
            "requested_resources_json": {
                "driver_vcpu": 4,
                "driver_memory_gb": 16,
                "executor_vcpu": 4,
                "executor_memory_gb": 14,
                "executor_instances": 7,
            },
            "instance_architecture": "mixed",
            "capacity_type": "spot",
            "max_runtime_minutes": 240,
            "tags_json": {"sparkpilot.default": "true", "size": "large"},
            "recommended_instance_types_json": ["m7g.2xlarge", "m7i.2xlarge", "r7g.2xlarge"],
        },
        {
            "name": "gpu",
            "description": "GPU Spark profile placeholder for GPU-enabled clusters.",
            "spark_conf_json": {
                "spark.kubernetes.executor.node.selector.eks.amazonaws.com/capacityType": "ON_DEMAND",
                "spark.executor.resource.gpu.amount": "1",
                "spark.task.resource.gpu.amount": "0.125",
            },
            "requested_resources_json": {
                "driver_vcpu": 4,
                "driver_memory_gb": 16,
                "executor_vcpu": 8,
                "executor_memory_gb": 32,
                "executor_instances": 2,
            },
            "instance_architecture": "x86_64",
            "capacity_type": "on_demand",
            "max_runtime_minutes": 240,
            "tags_json": {"sparkpilot.default": "true", "size": "gpu"},
            "recommended_instance_types_json": ["g5.xlarge", "g5.2xlarge"],
        },
    ]


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def ensure_default_golden_paths(db: Session) -> int:
    created = 0
    for spec in _default_golden_path_specs():
        existing = db.execute(
            select(GoldenPath).where(
                and_(
                    GoldenPath.environment_id.is_(None),
                    GoldenPath.name == spec["name"],
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        try:
            nested = db.begin_nested()  # SAVEPOINT so rollback only undoes this spec
            db.add(GoldenPath(environment_id=None, **spec))
            db.flush()
            created += 1
        except IntegrityError:
            nested.rollback()  # rolls back to SAVEPOINT, not the whole transaction
    if created:
        db.commit()
    return created


# ---------------------------------------------------------------------------
# Response payload builder
# ---------------------------------------------------------------------------

def _golden_path_to_response_payload(path: GoldenPath) -> dict[str, Any]:
    resources = path.requested_resources_json or {}
    driver_vcpu = int(resources.get("driver_vcpu", 1))
    driver_memory_gb = int(resources.get("driver_memory_gb", 4))
    executor_vcpu = int(resources.get("executor_vcpu", 1))
    executor_memory_gb = int(resources.get("executor_memory_gb", 4))
    executor_instances = int(resources.get("executor_instances", 1))
    return {
        "id": path.id,
        "environment_id": path.environment_id,
        "name": path.name,
        "description": path.description,
        "spark_config": dict(path.spark_conf_json or {}),
        "driver_resources": {"vcpu": driver_vcpu, "memory_gb": driver_memory_gb},
        "executor_resources": {"vcpu": executor_vcpu, "memory_gb": executor_memory_gb},
        "executor_count": executor_instances,
        "instance_architecture": path.instance_architecture,
        "capacity_type": path.capacity_type,
        "max_runtime_minutes": path.max_runtime_minutes,
        "tags": dict(path.tags_json or {}),
        "recommended_instance_types": list(path.recommended_instance_types_json or []),
        "created_at": path.created_at,
        "updated_at": path.updated_at,
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_golden_path(db: Session, req: GoldenPathCreate) -> GoldenPath:
    if req.environment_id:
        _require_environment(db, req.environment_id)
    existing = db.execute(
        select(GoldenPath).where(
            and_(
                GoldenPath.environment_id == req.environment_id,
                GoldenPath.name == req.name,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("Golden path name already exists.")
    record = GoldenPath(
        environment_id=req.environment_id,
        name=req.name,
        description=req.description,
        spark_conf_json=req.spark_config,
        requested_resources_json={
            "driver_vcpu": req.driver_resources.vcpu,
            "driver_memory_gb": req.driver_resources.memory_gb,
            "executor_vcpu": req.executor_resources.vcpu,
            "executor_memory_gb": req.executor_resources.memory_gb,
            "executor_instances": req.executor_count,
        },
        instance_architecture=req.instance_architecture,
        capacity_type=req.capacity_type,
        max_runtime_minutes=req.max_runtime_minutes,
        tags_json=req.tags,
        recommended_instance_types_json=req.recommended_instance_types,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_golden_paths(
    db: Session,
    environment_id: str | None = None,
    *,
    limit: int = 200,
    offset: int = 0,
    allowed_environment_ids: set[str] | None = None,
) -> list[GoldenPath]:
    stmt = select(GoldenPath)
    if environment_id:
        stmt = stmt.where(
            (GoldenPath.environment_id == environment_id) | (GoldenPath.environment_id.is_(None))
        )
    if allowed_environment_ids is not None:
        # Restrict to global paths (no environment) plus paths in allowed environments.
        stmt = stmt.where(
            GoldenPath.environment_id.is_(None) | GoldenPath.environment_id.in_(allowed_environment_ids)
        )
    stmt = stmt.order_by(GoldenPath.environment_id.desc(), GoldenPath.name.asc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars())


def get_golden_path(db: Session, golden_path_id: str) -> GoldenPath:
    item = db.get(GoldenPath, golden_path_id)
    if not item:
        raise EntityNotFoundError("Golden path not found.")
    return item


def _resolve_golden_path_for_run(db: Session, env: Environment, name: str) -> GoldenPath:
    item = db.execute(
        select(GoldenPath).where(
            and_(
                GoldenPath.name == name,
                (GoldenPath.environment_id == env.id) | (GoldenPath.environment_id.is_(None)),
            )
        ).order_by(GoldenPath.environment_id.desc())
    ).scalars().first()
    if not item:
        raise ValidationError(
            f"Golden path '{name}' was not found for this environment."
        )
    return item
