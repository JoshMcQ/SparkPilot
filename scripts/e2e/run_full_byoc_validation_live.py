#!/usr/bin/env python
"""Run live full-BYOC validation stages and capture evidence artifacts.

This script executes a real full-mode provisioning operation starting at the
validation phases (`validating_bootstrap`, `validating_runtime`) by seeding a
checkpoint that marks Terraform stages complete.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any

import boto3

FULL_BYOC_CHECKPOINT_AUDIT_ACTION = "environment.full_byoc_checkpoint"


def _utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _extract_role_name(role_arn: str) -> str:
    marker = ":role/"
    _, sep, suffix = role_arn.partition(marker)
    if not sep or not suffix.strip():
        raise ValueError(f"Invalid role ARN format: {role_arn}")
    return suffix.strip().split("/")[-1]


def _seed_full_byoc_checkpoint(
    *,
    actor: str,
    write_audit_event_fn,
    db,
    env,
    op,
) -> None:
    checkpoint = {
        "terraform_workspace": f"sp-{env.tenant_id[:8]}-{env.id[:8]}",
        "terraform_state_key": f"sparkpilot/full-byoc/{env.tenant_id}/{env.id}/terraform.tfstate",
        "last_successful_stage": "provisioning_emr",
        "attempt_count_by_stage": {
            "provisioning_network": 1,
            "provisioning_eks": 1,
            "provisioning_emr": 1,
        },
        "artifacts": [
            {
                "stage": "provisioning_emr",
                "attempt": 1,
                "kind": "seed",
                "ok": True,
                "summary": "seeded checkpoint for live validation-only proof run",
            }
        ],
    }
    write_audit_event_fn(
        db,
        actor=actor,
        action=FULL_BYOC_CHECKPOINT_AUDIT_ACTION,
        entity_type="environment",
        entity_id=env.id,
        tenant_id=env.tenant_id,
        details={
            "operation_id": op.id,
            "stage": "provisioning_emr",
            "checkpoint": checkpoint,
            "seeded_for_live_validation_proof": True,
        },
    )


def _gather_aws_context(
    *,
    region: str,
    emr_virtual_cluster_id: str,
    eks_cluster_name: str,
    execution_role_arn: str,
) -> dict[str, Any]:
    sts = boto3.client("sts", region_name=region)
    emr = boto3.client("emr-containers", region_name=region)
    eks = boto3.client("eks", region_name=region)
    iam = boto3.client("iam", region_name=region)
    execution_role_name = _extract_role_name(execution_role_arn)
    return {
        "captured_at": _iso_now(),
        "caller_identity": sts.get_caller_identity(),
        "virtual_cluster": emr.describe_virtual_cluster(id=emr_virtual_cluster_id),
        "eks_cluster": eks.describe_cluster(name=eks_cluster_name),
        "execution_role": iam.get_role(RoleName=execution_role_name),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run live full-BYOC validation proof flow.")
    parser.add_argument("--customer-role-arn", required=True, help="Customer role ARN for environment.customer_role_arn")
    parser.add_argument("--eks-cluster-arn", required=True, help="EKS cluster ARN to validate against")
    parser.add_argument("--emr-virtual-cluster-id", required=True, help="EMR virtual cluster ID to validate against")
    parser.add_argument("--eks-namespace", default="", help="Namespace; leave empty to infer from virtual cluster")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--actor", default="live-full-byoc-validation-proof", help="Audit actor label")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Base artifact directory")
    parser.add_argument("--database-url", default="sqlite:///./sparkpilot_live_full_byoc_validation.db")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    timestamp = _utc_timestamp()
    artifacts_dir = Path(args.artifacts_dir) / f"live-full-byoc-validation-{timestamp}"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Runtime settings are loaded from environment; set DB before importing
    # SparkPilot modules that initialize settings/engine globals.
    os.environ["SPARKPILOT_DATABASE_URL"] = args.database_url
    from sqlalchemy import and_, select
    from sparkpilot.audit import write_audit_event
    from sparkpilot.config import get_settings
    from sparkpilot.db import SessionLocal, init_db
    from sparkpilot.models import AuditEvent, Environment, ProvisioningOperation
    from sparkpilot.schemas import EnvironmentCreateRequest, TenantCreateRequest
    from sparkpilot.services import create_environment, create_tenant, process_provisioning_once

    settings = get_settings()

    init_db()

    with SessionLocal() as db:
        tenant = create_tenant(
            db,
            TenantCreateRequest(name=f"Live Full-BYOC Validation {timestamp}"),
            actor=args.actor,
            source_ip=None,
        )
        env, op = create_environment(
            db,
            EnvironmentCreateRequest(
                tenant_id=tenant.id,
                provisioning_mode="full",
                region=args.region,
                customer_role_arn=args.customer_role_arn,
                eks_cluster_arn=None,
                eks_namespace=None,
            ),
            actor=args.actor,
            source_ip=None,
            idempotency_key=f"live-full-byoc-validation-{timestamp}",
        )

        env.eks_cluster_arn = args.eks_cluster_arn.strip()
        env.emr_virtual_cluster_id = args.emr_virtual_cluster_id.strip()
        env.eks_namespace = args.eks_namespace.strip() or None

        op.state = "validating_bootstrap"
        op.step = "validating_bootstrap"
        op.message = "Seeded live proof run: starting at full-BYOC validation stages."
        _seed_full_byoc_checkpoint(
            actor=args.actor,
            write_audit_event_fn=write_audit_event,
            db=db,
            env=env,
            op=op,
        )
        db.commit()
        env_id = env.id
        op_id = op.id

    processed = 0
    run_error: str | None = None
    try:
        with SessionLocal() as db:
            processed = process_provisioning_once(db, actor=args.actor)
    except Exception as exc:  # noqa: BLE001
        run_error = str(exc)

    with SessionLocal() as db:
        latest_env = db.get(Environment, env_id)
        latest_op = db.get(ProvisioningOperation, op_id)
        if latest_env is None or latest_op is None:
            raise RuntimeError("Unable to reload environment/operation for evidence capture.")

        checkpoint_events = list(
            db.execute(
                select(AuditEvent)
                .where(
                    and_(
                        AuditEvent.action == FULL_BYOC_CHECKPOINT_AUDIT_ACTION,
                        AuditEvent.entity_type == "environment",
                        AuditEvent.entity_id == env_id,
                    )
                )
                .order_by(AuditEvent.created_at.asc())
            ).scalars()
        )
        latest_checkpoint: dict[str, Any] = {}
        if checkpoint_events:
            details = checkpoint_events[-1].details_json
            if isinstance(details, dict):
                checkpoint = details.get("checkpoint")
                if isinstance(checkpoint, dict):
                    latest_checkpoint = checkpoint

    eks_cluster_name = args.eks_cluster_arn.strip().split("/")[-1]
    aws_context = _gather_aws_context(
        region=args.region,
        emr_virtual_cluster_id=args.emr_virtual_cluster_id.strip(),
        eks_cluster_name=eks_cluster_name,
        execution_role_arn=settings.emr_execution_role_arn,
    )

    checkpoint_validation_artifacts = [
        item
        for item in latest_checkpoint.get("artifacts", [])
        if isinstance(item, dict) and item.get("kind") == "validation"
    ]
    summary = {
        "captured_at": _iso_now(),
        "processed_operations": processed,
        "run_error": run_error,
        "settings": {
            "database_url": settings.database_url,
            "dry_run_mode": settings.dry_run_mode,
            "enable_full_byoc_mode": settings.enable_full_byoc_mode,
            "emr_execution_role_arn": settings.emr_execution_role_arn,
        },
        "environment": {
            "id": latest_env.id,
            "tenant_id": latest_env.tenant_id,
            "status": latest_env.status,
            "region": latest_env.region,
            "provisioning_mode": latest_env.provisioning_mode,
            "customer_role_arn": latest_env.customer_role_arn,
            "eks_cluster_arn": latest_env.eks_cluster_arn,
            "eks_namespace": latest_env.eks_namespace,
            "emr_virtual_cluster_id": latest_env.emr_virtual_cluster_id,
        },
        "operation": {
            "id": latest_op.id,
            "state": latest_op.state,
            "step": latest_op.step,
            "message": latest_op.message,
            "logs_uri": latest_op.logs_uri,
        },
        "checkpoint": latest_checkpoint,
        "validation_artifacts": checkpoint_validation_artifacts,
        "aws_context_paths": {
            "aws_context.json": "aws_context.json",
            "checkpoint_events.json": "checkpoint_events.json",
        },
        "succeeded": latest_env.status == "ready" and latest_op.state == "ready" and run_error is None,
    }

    checkpoint_event_rows = []
    for event in checkpoint_events:
        checkpoint_event_rows.append(
            {
                "id": event.id,
                "created_at": event.created_at.isoformat(),
                "action": event.action,
                "details": event.details_json,
            }
        )

    (artifacts_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (artifacts_dir / "aws_context.json").write_text(json.dumps(aws_context, indent=2, default=str), encoding="utf-8")
    (artifacts_dir / "checkpoint_events.json").write_text(
        json.dumps(checkpoint_event_rows, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"Artifacts: {artifacts_dir}")
    print(
        "Result: "
        f"environment_status={latest_env.status} "
        f"operation_state={latest_op.state} "
        f"succeeded={summary['succeeded']}"
    )
    return 0 if summary["succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
