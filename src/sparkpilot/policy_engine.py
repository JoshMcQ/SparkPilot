"""Policy engine for run guardrails (#39).

Evaluates configured policies against run parameters during preflight,
returning clear pass/fail/warn results with remediation guidance.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sparkpilot.audit import write_audit_event
from sparkpilot.models import Environment, Policy, POLICY_RULE_TYPES


# ---------------------------------------------------------------------------
# Policy CRUD helpers
# ---------------------------------------------------------------------------


def create_policy(
    db: Session,
    *,
    name: str,
    scope: str,
    scope_id: str | None,
    rule_type: str,
    config: dict,
    enforcement: str,
    active: bool = True,
    actor: str | None = None,
    source_ip: str | None = None,
) -> Policy:
    if rule_type not in POLICY_RULE_TYPES:
        raise ValueError(f"Unknown policy rule_type '{rule_type}'.")
    policy = Policy(
        name=name,
        scope=scope,
        scope_id=scope_id,
        rule_type=rule_type,
        config_json=config,
        enforcement=enforcement,
        active=active,
        created_by_actor=actor,
    )
    db.add(policy)
    db.flush()
    write_audit_event(
        db,
        actor=actor or "system",
        action="policy.created",
        entity_type="policy",
        entity_id=policy.id,
        source_ip=source_ip,
        details={"name": name, "rule_type": rule_type, "scope": scope, "enforcement": enforcement},
    )
    db.commit()
    db.refresh(policy)
    return policy


def list_policies(
    db: Session,
    *,
    scope: str | None = None,
    scope_id: str | None = None,
    active_only: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> list[Policy]:
    stmt = select(Policy)
    if scope:
        stmt = stmt.where(Policy.scope == scope)
    if scope_id:
        stmt = stmt.where(Policy.scope_id == scope_id)
    if active_only:
        stmt = stmt.where(Policy.active.is_(True))
    stmt = stmt.order_by(Policy.created_at.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def get_policy(db: Session, policy_id: str) -> Policy | None:
    return db.get(Policy, policy_id)


def delete_policy(
    db: Session,
    policy_id: str,
    *,
    actor: str | None = None,
    source_ip: str | None = None,
) -> bool:
    policy = db.get(Policy, policy_id)
    if policy is None:
        return False
    policy.active = False
    write_audit_event(
        db,
        actor=actor or "system",
        action="policy.deactivated",
        entity_type="policy",
        entity_id=policy_id,
        source_ip=source_ip,
        details={"name": policy.name, "rule_type": policy.rule_type},
    )
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Policy evaluation engine
# ---------------------------------------------------------------------------


def _resolve_applicable_policies(
    db: Session,
    environment: Environment,
) -> list[Policy]:
    """Return active policies matching environment scope hierarchy (global → tenant → environment)."""
    stmt = select(Policy).where(
        Policy.active.is_(True),
        (
            (Policy.scope == "global")
            | ((Policy.scope == "tenant") & (Policy.scope_id == environment.tenant_id))
            | ((Policy.scope == "environment") & (Policy.scope_id == environment.id))
        ),
    )
    return list(db.execute(stmt).scalars().all())


def _evaluate_max_runtime_seconds(
    policy: Policy,
    *,
    timeout_seconds: int | None,
    **_: Any,
) -> dict:
    limit = int(policy.config_json.get("max_seconds", 0))
    if limit <= 0:
        return {"passed": True, "message": "max_runtime_seconds policy has no effective limit."}
    effective = timeout_seconds or 7200
    if effective > limit:
        return {
            "passed": False,
            "message": f"Run timeout ({effective}s) exceeds policy limit ({limit}s).",
            "remediation": f"Set timeout_seconds to {limit} or less, or request a policy exception.",
        }
    return {"passed": True, "message": f"Run timeout ({effective}s) is within policy limit ({limit}s)."}


def _evaluate_max_vcpu(
    policy: Policy,
    *,
    requested_resources: dict | None,
    **_: Any,
) -> dict:
    limit = int(policy.config_json.get("max_vcpu", 0))
    if limit <= 0:
        return {"passed": True, "message": "max_vcpu policy has no effective limit."}
    resources = requested_resources or {}
    driver_vcpu = int(resources.get("driver_vcpu", 1))
    executor_vcpu = int(resources.get("executor_vcpu", 1))
    executor_instances = int(resources.get("executor_instances", 1))
    total_vcpu = driver_vcpu + (executor_vcpu * executor_instances)
    if total_vcpu > limit:
        return {
            "passed": False,
            "message": f"Requested vCPU ({total_vcpu}) exceeds policy limit ({limit}).",
            "remediation": f"Reduce total vCPU to {limit} or less.",
        }
    return {"passed": True, "message": f"Requested vCPU ({total_vcpu}) is within policy limit ({limit})."}


def _evaluate_max_memory_gb(
    policy: Policy,
    *,
    requested_resources: dict | None,
    **_: Any,
) -> dict:
    limit = int(policy.config_json.get("max_memory_gb", 0))
    if limit <= 0:
        return {"passed": True, "message": "max_memory_gb policy has no effective limit."}
    resources = requested_resources or {}
    driver_mem = int(resources.get("driver_memory_gb", 4))
    executor_mem = int(resources.get("executor_memory_gb", 4))
    executor_instances = int(resources.get("executor_instances", 1))
    total_mem = driver_mem + (executor_mem * executor_instances)
    if total_mem > limit:
        return {
            "passed": False,
            "message": f"Requested memory ({total_mem}GB) exceeds policy limit ({limit}GB).",
            "remediation": f"Reduce total memory to {limit}GB or less.",
        }
    return {"passed": True, "message": f"Requested memory ({total_mem}GB) is within policy limit ({limit}GB)."}


def _evaluate_required_tags(
    policy: Policy,
    *,
    spark_conf: dict | None,
    **_: Any,
) -> dict:
    required = policy.config_json.get("tags", {})
    if not required:
        return {"passed": True, "message": "No required tags configured."}
    conf = spark_conf or {}
    missing = []
    for tag_key, expected_value in required.items():
        conf_key = f"spark.kubernetes.driver.label.{tag_key}"
        actual = conf.get(conf_key, "")
        if expected_value and actual != expected_value:
            missing.append(f"{tag_key}={expected_value}")
        elif not expected_value and not actual:
            missing.append(tag_key)
    if missing:
        return {
            "passed": False,
            "message": f"Missing required tags: {', '.join(missing)}.",
            "remediation": "Add required tags to spark_conf as spark.kubernetes.driver.label.<tag>.",
        }
    return {"passed": True, "message": "All required tags present."}


def _evaluate_allowed_golden_paths(
    policy: Policy,
    *,
    golden_path: str | None,
    **_: Any,
) -> dict:
    allowed = policy.config_json.get("allowed", [])
    if not allowed:
        return {"passed": True, "message": "No golden path restrictions configured."}
    if not golden_path:
        require = policy.config_json.get("require_golden_path", False)
        if require:
            return {
                "passed": False,
                "message": "A golden path is required by policy.",
                "remediation": f"Specify one of: {', '.join(allowed)}.",
            }
        return {"passed": True, "message": "No golden path specified (not required)."}
    if golden_path not in allowed:
        return {
            "passed": False,
            "message": f"Golden path '{golden_path}' is not in the allowed list.",
            "remediation": f"Use one of: {', '.join(allowed)}.",
        }
    return {"passed": True, "message": f"Golden path '{golden_path}' is allowed."}


def _evaluate_allowed_release_labels(
    policy: Policy,
    *,
    release_label: str | None,
    **_: Any,
) -> dict:
    allowed = policy.config_json.get("allowed", [])
    if not allowed:
        return {"passed": True, "message": "No release label restrictions configured."}
    if not release_label:
        return {"passed": True, "message": "No explicit release label specified."}
    if release_label not in allowed:
        return {
            "passed": False,
            "message": f"Release label '{release_label}' is not allowed by policy.",
            "remediation": f"Use one of: {', '.join(allowed)}.",
        }
    return {"passed": True, "message": f"Release label '{release_label}' is allowed."}


def _evaluate_allowed_instance_types(
    policy: Policy,
    *,
    spark_conf: dict | None,
    **_: Any,
) -> dict:
    allowed = policy.config_json.get("allowed", [])
    if not allowed:
        return {"passed": True, "message": "No instance type restrictions configured."}
    conf = spark_conf or {}
    node_selector_key = "spark.kubernetes.node.selector.node.kubernetes.io/instance-type"
    instance_type = conf.get(node_selector_key, "")
    if not instance_type:
        return {"passed": True, "message": "No explicit instance type selector specified."}
    if instance_type not in allowed:
        return {
            "passed": False,
            "message": f"Instance type '{instance_type}' is not allowed by policy.",
            "remediation": f"Use one of: {', '.join(allowed)}.",
        }
    return {"passed": True, "message": f"Instance type '{instance_type}' is allowed."}


def _evaluate_allowed_security_configurations(
    policy: Policy,
    *,
    security_configuration_id: str | None,
    **_: Any,
) -> dict:
    allowed = policy.config_json.get("allowed", [])
    required = policy.config_json.get("require_security_configuration", False)
    if not allowed and not required:
        return {"passed": True, "message": "No security configuration restrictions configured."}
    if not security_configuration_id:
        if required:
            return {
                "passed": False,
                "message": "A security configuration is required by policy.",
                "remediation": f"Associate one of: {', '.join(allowed)}." if allowed else "Associate a security configuration.",
            }
        return {"passed": True, "message": "No security configuration specified (not required)."}
    if allowed and security_configuration_id not in allowed:
        return {
            "passed": False,
            "message": f"Security configuration '{security_configuration_id}' is not in the allowed list.",
            "remediation": f"Use one of: {', '.join(allowed)}.",
        }
    return {"passed": True, "message": f"Security configuration '{security_configuration_id}' is allowed."}


_RULE_EVALUATORS = {
    "max_runtime_seconds": _evaluate_max_runtime_seconds,
    "max_vcpu": _evaluate_max_vcpu,
    "max_memory_gb": _evaluate_max_memory_gb,
    "required_tags": _evaluate_required_tags,
    "allowed_golden_paths": _evaluate_allowed_golden_paths,
    "allowed_release_labels": _evaluate_allowed_release_labels,
    "allowed_instance_types": _evaluate_allowed_instance_types,
    "allowed_security_configurations": _evaluate_allowed_security_configurations,
}


def evaluate_policies(
    db: Session,
    environment: Environment,
    *,
    timeout_seconds: int | None = None,
    requested_resources: dict | None = None,
    spark_conf: dict | None = None,
    golden_path: str | None = None,
    release_label: str | None = None,
    security_configuration_id: str | None = None,
    actor: str = "system",
    source_ip: str | None = None,
    commit: bool = False,
) -> list[dict]:
    """Evaluate all applicable policies for a run.

    Returns a list of evaluation result dicts, each containing:
    policy_id, policy_name, rule_type, enforcement, passed, message, remediation.
    """
    policies = _resolve_applicable_policies(db, environment)
    results = []
    for policy in policies:
        evaluator = _RULE_EVALUATORS.get(policy.rule_type)
        if evaluator is None:
            continue
        result = evaluator(
            policy,
            timeout_seconds=timeout_seconds,
            requested_resources=requested_resources,
            spark_conf=spark_conf,
            golden_path=golden_path,
            release_label=release_label,
            security_configuration_id=security_configuration_id,
        )
        entry = {
            "policy_id": policy.id,
            "policy_name": policy.name,
            "rule_type": policy.rule_type,
            "enforcement": policy.enforcement,
            "passed": result["passed"],
            "message": result["message"],
            "remediation": result.get("remediation"),
        }
        results.append(entry)
        # Audit each evaluation
        write_audit_event(
            db,
            actor=actor,
            action="policy.evaluated",
            entity_type="policy",
            entity_id=policy.id,
            source_ip=source_ip,
            details={
                "policy_name": policy.name,
                "rule_type": policy.rule_type,
                "enforcement": policy.enforcement,
                "passed": result["passed"],
                "environment_id": environment.id,
            },
        )
    if commit:
        db.commit()
    return results


def policy_to_dict(p: Policy) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "scope": p.scope,
        "scope_id": p.scope_id,
        "rule_type": p.rule_type,
        "config": p.config_json,
        "enforcement": p.enforcement,
        "active": p.active,
        "created_by_actor": p.created_by_actor,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }
