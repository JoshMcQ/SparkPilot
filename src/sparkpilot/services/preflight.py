"""Environment and run preflight checks with TTL caching."""

from collections import OrderedDict
import hashlib
import json
import logging
import threading
import time
from typing import Any, Callable

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from sparkpilot.config import get_settings, is_valid_iam_role_arn, validate_runtime_settings
from sparkpilot.db import SessionLocal
from sparkpilot.models import AuditEvent, EmrRelease, Environment, Run, TeamBudget
from sparkpilot.services._helpers import _now, _validate_custom_spark_conf_policy
from sparkpilot.services.emr_releases import _canonical_release_label
from sparkpilot.services.finops import _billing_period, _team_key_for_environment, _team_spend_for_period
from sparkpilot.services.preflight_byoc import _add_byoc_lite_configuration_checks  # noqa: F401

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PREFLIGHT_AUDIT_ACTIONS = {"run.preflight_passed", "run.preflight_failed", "run.preflight_diagnostic"}


# ---------------------------------------------------------------------------
# Preflight TTL cache for scheduler hot path
# ---------------------------------------------------------------------------

_PREFLIGHT_CACHE_TTL_SECONDS = 300  # 5 minutes
_PREFLIGHT_CACHE_MAX_ENTRIES = 1024
_preflight_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_preflight_cache_lock = threading.Lock()


def _spark_conf_cache_fingerprint(spark_conf: dict[str, str] | None) -> str:
    payload = json.dumps(spark_conf or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _environment_cache_fingerprint(environment: Environment) -> str:
    payload = {
        "id": environment.id,
        "status": environment.status,
        "region": environment.region,
        "tenant_id": environment.tenant_id,
        "instance_architecture": environment.instance_architecture,
        "customer_role_arn": environment.customer_role_arn,
        "eks_cluster_arn": environment.eks_cluster_arn,
        "eks_namespace": environment.eks_namespace,
        "emr_virtual_cluster_id": environment.emr_virtual_cluster_id,
        "updated_at": environment.updated_at.isoformat() if environment.updated_at else "",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _preflight_cache_key(environment: Environment, spark_conf: dict[str, str] | None) -> str:
    return f"{_environment_cache_fingerprint(environment)}:{_spark_conf_cache_fingerprint(spark_conf)}"


def _trim_preflight_cache(now: float) -> None:
    stale_keys = [
        cache_key
        for cache_key, (cached_at, _) in _preflight_cache.items()
        if now - cached_at >= _PREFLIGHT_CACHE_TTL_SECONDS
    ]
    for cache_key in stale_keys:
        _preflight_cache.pop(cache_key, None)
    while len(_preflight_cache) > _PREFLIGHT_CACHE_MAX_ENTRIES:
        _preflight_cache.popitem(last=False)


# ---------------------------------------------------------------------------
# Runtime / release preflight checks
# ---------------------------------------------------------------------------

def _add_runtime_and_release_preflight_checks(
    *,
    settings: Any,
    environment: Environment,
    db: Session | None,
    add_check: Callable[..., None],
) -> None:
    _add_execution_role_config_check(settings=settings, add_check=add_check)
    _add_log_group_prefix_check(settings=settings, add_check=add_check)
    configured_release_label = settings.emr_release_label.strip()
    if not configured_release_label:
        _add_missing_release_label_checks(
            instance_architecture=environment.instance_architecture,
            add_check=add_check,
        )
        return

    add_check(
        code="config.emr_release_label",
        status_value="pass",
        message="EMR release label is configured.",
        details={"emr_release_label": settings.emr_release_label},
    )
    release_row = _lookup_release_row(
        configured_release_label=configured_release_label,
        db=db,
    )
    _add_release_currency_check(
        configured_release_label=configured_release_label,
        release_row=release_row,
        add_check=add_check,
    )
    _add_graviton_support_check(
        instance_architecture=environment.instance_architecture,
        release_row=release_row,
        add_check=add_check,
    )


def _add_execution_role_config_check(*, settings: Any, add_check: Callable[..., None]) -> None:
    try:
        validate_runtime_settings(settings)
        add_check(
            code="config.execution_role",
            status_value="pass",
            message="Execution role configuration is valid for runtime mode.",
            details={
                "dry_run_mode": settings.dry_run_mode,
                "execution_role_arn": settings.emr_execution_role_arn.strip(),
            },
        )
        return
    except ValueError as exc:
        add_check(
            code="config.execution_role",
            status_value="fail",
            message=str(exc),
            remediation=(
                "Set SPARKPILOT_EMR_EXECUTION_ROLE_ARN to a real IAM role ARN and restart API/workers."
            ),
            details={
                "dry_run_mode": settings.dry_run_mode,
                "execution_role_arn": settings.emr_execution_role_arn.strip(),
            },
        )


def _add_log_group_prefix_check(*, settings: Any, add_check: Callable[..., None]) -> None:
    if settings.log_group_prefix.strip():
        add_check(
            code="config.log_group_prefix",
            status_value="pass",
            message="CloudWatch log group prefix is configured.",
            details={"log_group_prefix": settings.log_group_prefix},
        )
    else:
        add_check(
            code="config.log_group_prefix",
            status_value="fail",
            message="SPARKPILOT_LOG_GROUP_PREFIX is empty.",
            remediation="Set SPARKPILOT_LOG_GROUP_PREFIX to a non-empty CloudWatch log group prefix.",
        )


def _lookup_release_row(*, configured_release_label: str, db: Session | None) -> EmrRelease | None:
    canonical_release_label = _canonical_release_label(configured_release_label)

    def _load(session: Session) -> EmrRelease | None:
        return session.execute(
            select(EmrRelease).where(
                or_(
                    EmrRelease.release_label == configured_release_label,
                    EmrRelease.release_label == canonical_release_label,
                )
            )
        ).scalar_one_or_none()

    if db is not None:
        return _load(db)
    with SessionLocal() as check_db:
        return _load(check_db)


def _add_release_currency_check(
    *,
    configured_release_label: str,
    release_row: EmrRelease | None,
    add_check: Callable[..., None],
) -> None:
    if release_row is None:
        add_check(
            code="config.emr_release_currency",
            status_value="warning",
            message="Release currency is unknown because this label has not been synced yet.",
            remediation="Run the EMR release sync worker and retry preflight.",
            details={"release_label": configured_release_label},
        )
        return

    if release_row.lifecycle_status == "current":
        add_check(
            code="config.emr_release_currency",
            status_value="pass",
            message="Configured EMR release is current.",
            details={"release_label": configured_release_label},
        )
        return

    if release_row.lifecycle_status == "deprecated":
        add_check(
            code="config.emr_release_currency",
            status_value="warning",
            message="Configured EMR release is deprecated.",
            remediation=(
                f"Upgrade to {release_row.upgrade_target} or newer and re-run environment preflight."
                if release_row.upgrade_target
                else "Upgrade to a current EMR release label and re-run environment preflight."
            ),
            details={"release_label": configured_release_label},
        )
        return

    add_check(
        code="config.emr_release_currency",
        status_value="fail",
        message="Configured EMR release is end-of-life.",
        remediation=(
            f"Upgrade to {release_row.upgrade_target} or newer before submitting runs."
            if release_row.upgrade_target
            else "Upgrade to a current EMR release label before submitting runs."
        ),
        details={"release_label": configured_release_label},
    )


def _add_graviton_support_check(
    *,
    instance_architecture: str,
    release_row: EmrRelease | None,
    add_check: Callable[..., None],
) -> None:
    if instance_architecture not in {"arm64", "mixed"}:
        add_check(
            code="config.graviton_release_support",
            status_value="pass",
            message="x86_64 architecture selected; Graviton compatibility check is not required.",
            details={"instance_architecture": instance_architecture},
        )
        return

    if release_row and release_row.graviton_supported:
        add_check(
            code="config.graviton_release_support",
            status_value="pass",
            message="Configured EMR release supports Graviton/ARM workloads.",
            details={"instance_architecture": instance_architecture},
        )
        return

    if instance_architecture == "arm64":
        add_check(
            code="config.graviton_release_support",
            status_value="fail",
            message="Configured EMR release does not confirm Graviton support for arm64-only workloads.",
            remediation="Select a Graviton-capable EMR release label (for example >= emr-6.9.0).",
            details={"instance_architecture": instance_architecture},
        )
        return

    add_check(
        code="config.graviton_release_support",
        status_value="warning",
        message="Graviton support could not be confirmed for mixed-architecture workloads.",
        remediation="Run release sync and prefer a Graviton-capable EMR release label.",
        details={"instance_architecture": instance_architecture},
    )


def _add_missing_release_label_checks(
    *,
    instance_architecture: str,
    add_check: Callable[..., None],
) -> None:
    add_check(
        code="config.emr_release_label",
        status_value="fail",
        message="SPARKPILOT_EMR_RELEASE_LABEL is empty.",
        remediation="Set SPARKPILOT_EMR_RELEASE_LABEL to a valid EMR on EKS release label.",
    )
    add_check(
        code="config.emr_release_currency",
        status_value="fail",
        message="Release currency cannot be evaluated because release label is missing.",
        remediation="Set SPARKPILOT_EMR_RELEASE_LABEL and run release sync.",
    )
    if instance_architecture in {"arm64", "mixed"}:
        add_check(
            code="config.graviton_release_support",
            status_value="fail" if instance_architecture == "arm64" else "warning",
            message="Graviton compatibility cannot be evaluated because release label is missing.",
            remediation="Set SPARKPILOT_EMR_RELEASE_LABEL and run release sync.",
            details={"instance_architecture": instance_architecture},
        )
        return
    add_check(
        code="config.graviton_release_support",
        status_value="pass",
        message="x86_64 architecture selected; Graviton compatibility check is not required.",
        details={"instance_architecture": instance_architecture},
    )


# ---------------------------------------------------------------------------
# Team budget preflight checks
# ---------------------------------------------------------------------------

def _add_team_budget_preflight_checks(
    *,
    environment: Environment,
    db: Session | None,
    add_check: Callable[..., None],
) -> None:
    team_key = _team_key_for_environment(environment)
    current_period = _billing_period()

    def _evaluate_team_budget(session: Session) -> None:
        budget = session.execute(select(TeamBudget).where(TeamBudget.team == team_key)).scalar_one_or_none()
        if budget is None:
            add_check(
                code="team_budget",
                status_value="pass",
                message="No team budget is configured for this team.",
                details={"team": team_key, "period": current_period},
            )
            return

        _, _, effective_spend = _team_spend_for_period(session, team_key, current_period)
        warn_threshold = int(budget.monthly_budget_usd_micros * budget.warn_threshold_pct / 100)
        block_threshold = int(budget.monthly_budget_usd_micros * budget.block_threshold_pct / 100)
        if effective_spend >= block_threshold:
            add_check(
                code="team_budget",
                status_value="fail",
                message="Team budget block threshold exceeded for the current billing period.",
                remediation="Increase team budget or reduce run volume/resource usage before submitting new runs.",
                details={
                    "team": team_key,
                    "period": current_period,
                    "effective_spend_usd_micros": effective_spend,
                    "block_threshold_usd_micros": block_threshold,
                },
            )
        elif effective_spend >= warn_threshold:
            add_check(
                code="team_budget",
                status_value="warning",
                message="Team budget warning threshold reached for the current billing period.",
                remediation="Review spend and planned workloads before submitting large runs.",
                details={
                    "team": team_key,
                    "period": current_period,
                    "effective_spend_usd_micros": effective_spend,
                    "warn_threshold_usd_micros": warn_threshold,
                },
            )
        else:
            add_check(
                code="team_budget",
                status_value="pass",
                message="Team budget check passed for the current billing period.",
                details={
                    "team": team_key,
                    "period": current_period,
                    "effective_spend_usd_micros": effective_spend,
                    "budget_usd_micros": budget.monthly_budget_usd_micros,
                },
            )

    if db is not None:
        _evaluate_team_budget(db)
    else:
        with SessionLocal() as budget_db:
            _evaluate_team_budget(budget_db)


# ---------------------------------------------------------------------------
# Core preflight checks (environment + spark conf policy)
# ---------------------------------------------------------------------------

def _add_customer_role_arn_check(*, environment: Environment, add_check: Callable[..., None]) -> None:
    if is_valid_iam_role_arn(environment.customer_role_arn):
        add_check(
            code="environment.customer_role_arn",
            status_value="pass",
            message="customer_role_arn looks like a valid IAM role ARN.",
        )
        return
    add_check(
        code="environment.customer_role_arn",
        status_value="fail",
        message="customer_role_arn is not a valid IAM role ARN.",
        remediation="Set customer_role_arn to arn:aws:iam::<account-id>:role/<role-name>.",
    )


def _add_environment_status_check(
    *,
    environment: Environment,
    require_environment_ready: bool,
    add_check: Callable[..., None],
) -> None:
    if not require_environment_ready:
        return
    if environment.status == "ready":
        add_check(
            code="environment.status",
            status_value="pass",
            message="Environment is in ready state.",
        )
        return
    add_check(
        code="environment.status",
        status_value="fail",
        message=f"Environment status is {environment.status}, expected ready.",
        remediation="Wait for environment provisioning to complete before submitting runs.",
        details={"status": environment.status},
    )


def _add_virtual_cluster_check(
    *,
    environment: Environment,
    require_virtual_cluster: bool,
    add_check: Callable[..., None],
) -> None:
    if not require_virtual_cluster:
        return
    if environment.emr_virtual_cluster_id:
        add_check(
            code="environment.virtual_cluster",
            status_value="pass",
            message="EMR virtual cluster is configured.",
        )
        return
    add_check(
        code="environment.virtual_cluster",
        status_value="fail",
        message="EMR virtual cluster id is missing.",
        remediation="Ensure provisioning completed and emr_virtual_cluster_id is set.",
    )


def _add_spark_conf_policy_check(
    *,
    spark_conf: dict[str, str] | None,
    add_check: Callable[..., None],
) -> None:
    blocked_spark_conf_keys = _validate_custom_spark_conf_policy(spark_conf)
    if blocked_spark_conf_keys:
        add_check(
            code="run.spark_conf_policy",
            status_value="fail",
            message="Spark configuration includes blocked keys for this environment policy.",
            remediation="Remove blocked Spark keys related to Kubernetes auth/service-account overrides and retry.",
            details={"blocked_keys": ", ".join(blocked_spark_conf_keys)},
        )
        return
    add_check(
        code="run.spark_conf_policy",
        status_value="pass",
        message="Spark configuration policy checks passed.",
    )


# ---------------------------------------------------------------------------
# Supplemental spark-conf preflight checks (VPA, S3 Express)
# ---------------------------------------------------------------------------

def _check_vpa_compat(env: Any, spark_conf: dict[str, str] | None) -> dict[str, Any]:
    """Emit a WARNING if VPA-incompatible spark conf is detected.

    VPA can only resize pods on restart; very low batch sizes combined with
    VPA admission can cause unexpected resource contention. This is advisory
    only — it does not block job submission.
    """
    spark_conf = spark_conf or {}
    issues = []
    batch_size_str = spark_conf.get("spark.kubernetes.allocation.batch.size", "")
    if batch_size_str:
        try:
            batch_size = int(batch_size_str)
            if batch_size <= 5:
                issues.append(
                    f"spark.kubernetes.allocation.batch.size is set to {batch_size}, which is very low. "
                    "If a VPA admission controller is active in this namespace, executor pods may be "
                    "rejected or resized on creation, leading to allocation delays. "
                    "Consider raising batch size or setting VPA mode to 'Off' for Spark workloads."
                )
        except ValueError:
            pass
    return {
        "status": "warn" if issues else "pass",
        "check": "vpa_compat",
        "issues": issues,
    }


def _check_s3_express_config(spark_conf: dict[str, str]) -> dict[str, Any]:
    """Warn when S3 Express shuffle is configured without co-location pin."""
    issues = []
    uses_s3_express = any(
        "s3express" in str(v).lower() or "s3express" in str(k).lower()
        for k, v in spark_conf.items()
    )
    if not uses_s3_express:
        return {"status": "pass", "check": "s3_express_config", "issues": []}

    has_az_affinity = "spark.kubernetes.node.selector.topology.kubernetes.io/zone" in spark_conf
    if not has_az_affinity:
        issues.append(
            "S3 Express shuffle detected but no AZ affinity node selector configured. "
            "Set spark.kubernetes.node.selector.topology.kubernetes.io/zone to pin pods "
            "to the same AZ as your S3 Express bucket to avoid cross-AZ charges."
        )
    return {
        "status": "warn" if issues else "pass",
        "check": "s3_express_config",
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# YuniKorn queue capacity check
# ---------------------------------------------------------------------------

def _check_yunikorn_queue_capacity(
    environment: Environment,
    run: Run | None,
    add_check: Callable[..., None],
) -> None:
    """Block run if environment has a YuniKorn queue and run would exceed queue max vCPU."""
    if not environment.yunikorn_queue or not environment.yunikorn_queue_max_vcpu:
        add_check(
            code="yunikorn_queue_capacity",
            status_value="pass",
            message="YuniKorn queue capacity check is not applicable.",
        )
        return

    if run is None:
        add_check(
            code="yunikorn_queue_capacity",
            status_value="pass",
            message="YuniKorn queue is configured; per-run capacity check requires a run context.",
            details={
                "yunikorn_queue": environment.yunikorn_queue,
                "queue_max_vcpu": environment.yunikorn_queue_max_vcpu,
            },
        )
        return

    resources = run.requested_resources_json or {}
    executor_vcpu = resources.get("executor_vcpu", 0)
    executor_instances = resources.get("executor_instances", 0)
    driver_vcpu = resources.get("driver_vcpu", 0)
    requested_vcpu = executor_vcpu * executor_instances + driver_vcpu

    if requested_vcpu > environment.yunikorn_queue_max_vcpu:
        add_check(
            code="yunikorn_queue_capacity",
            status_value="fail",
            message=(
                f"Run requests {requested_vcpu} vCPU but YuniKorn queue max is "
                f"{environment.yunikorn_queue_max_vcpu}."
            ),
            remediation=(
                "Reduce executor_vcpu, executor_instances, or driver_vcpu, "
                "or increase yunikorn_queue_max_vcpu on the environment."
            ),
            details={
                "requested_vcpu": requested_vcpu,
                "queue_max_vcpu": environment.yunikorn_queue_max_vcpu,
                "yunikorn_queue": environment.yunikorn_queue,
            },
        )
        return

    add_check(
        code="yunikorn_queue_capacity",
        status_value="pass",
        message="Run vCPU request is within YuniKorn queue capacity.",
        details={
            "requested_vcpu": requested_vcpu,
            "queue_max_vcpu": environment.yunikorn_queue_max_vcpu,
            "yunikorn_queue": environment.yunikorn_queue,
        },
    )


# ---------------------------------------------------------------------------
# Policy engine integration (#39)
# ---------------------------------------------------------------------------


def _add_policy_engine_checks(
    *,
    environment: Environment,
    spark_conf: dict[str, str] | None,
    run: "Run | None",
    db: Session | None,
    add_check: Callable[..., None],
) -> None:
    """Evaluate applicable policies and convert results to preflight checks."""
    from sparkpilot.policy_engine import evaluate_policies

    def _run_eval(session: Session) -> list[dict]:
        timeout_seconds = None
        requested_resources = None
        golden_path = None
        if run is not None:
            timeout_seconds = getattr(run, "timeout_seconds", None)
            rr_json = getattr(run, "requested_resources_json", None)
            if rr_json and isinstance(rr_json, dict):
                requested_resources = rr_json
            golden_path = getattr(run, "golden_path_name", None)
        return evaluate_policies(
            session,
            environment,
            timeout_seconds=timeout_seconds,
            requested_resources=requested_resources,
            spark_conf=spark_conf,
            golden_path=golden_path,
        )

    if db is not None:
        results = _run_eval(db)
    else:
        with SessionLocal() as policy_db:
            results = _run_eval(policy_db)
            policy_db.commit()  # persist audit events when we own the session

    for r in results:
        if r["passed"]:
            add_check(
                code=f"policy.{r['rule_type']}",
                status_value="pass",
                message=r["message"],
                details={"policy_id": r["policy_id"], "policy_name": r["policy_name"]},
            )
        else:
            status_value = "fail" if r["enforcement"] == "hard" else "warning"
            add_check(
                code=f"policy.{r['rule_type']}",
                status_value=status_value,
                message=r["message"],
                remediation=r.get("remediation"),
                details={"policy_id": r["policy_id"], "policy_name": r["policy_name"]},
            )


# ---------------------------------------------------------------------------
# Preflight builder
# ---------------------------------------------------------------------------

def _build_preflight(
    environment: Environment,
    run_id: str | None = None,
    *,
    spark_conf: dict[str, str] | None = None,
    require_environment_ready: bool = True,
    require_virtual_cluster: bool = True,
    db: Session | None = None,
    run: Run | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    checks: list[dict[str, Any]] = []

    # Resolve run object for per-run checks (e.g. YuniKorn capacity)
    _run_obj: Run | None = run
    if _run_obj is None and run_id is not None:
        def _load_run(session: Session) -> Run | None:
            return session.get(Run, run_id)
        if db is not None:
            _run_obj = _load_run(db)
        else:
            with SessionLocal() as _rdb:
                _run_obj = _load_run(_rdb)

    def add_check(
        *,
        code: str,
        status_value: str,
        message: str,
        remediation: str | None = None,
        details: dict[str, str | int | bool] | None = None,
    ) -> None:
        checks.append(
            {
                "code": code,
                "status": status_value,
                "message": message,
                "remediation": remediation,
                "details": details or {},
            }
        )

    _add_runtime_and_release_preflight_checks(
        settings=settings,
        environment=environment,
        db=db,
        add_check=add_check,
    )
    _add_customer_role_arn_check(environment=environment, add_check=add_check)
    _add_environment_status_check(
        environment=environment,
        require_environment_ready=require_environment_ready,
        add_check=add_check,
    )
    _add_virtual_cluster_check(
        environment=environment,
        require_virtual_cluster=require_virtual_cluster,
        add_check=add_check,
    )
    _add_spark_conf_policy_check(spark_conf=spark_conf, add_check=add_check)

    _add_team_budget_preflight_checks(
        environment=environment,
        db=db,
        add_check=add_check,
    )

    _check_yunikorn_queue_capacity(environment, _run_obj, add_check)

    _add_byoc_lite_configuration_checks(
        environment=environment,
        spark_conf=spark_conf,
        add_check=add_check,
    )

    # Supplemental spark-conf checks (advisory warnings, not blocks)
    _effective_spark_conf = spark_conf or {}

    vpa_result = _check_vpa_compat(environment, _effective_spark_conf)
    if vpa_result["issues"]:
        for _issue in vpa_result["issues"]:
            add_check(
                code="run.vpa_compat",
                status_value="warning",
                message=_issue,
                remediation=(
                    "Review VPA admission controller configuration for this namespace. "
                    "Set VPA mode to 'Off' or 'Initial' for Spark workloads, or raise "
                    "spark.kubernetes.allocation.batch.size above 5."
                ),
            )

    s3_express_result = _check_s3_express_config(_effective_spark_conf)
    if s3_express_result["issues"]:
        for _issue in s3_express_result["issues"]:
            add_check(
                code="run.s3_express_config",
                status_value="warning",
                message=_issue,
                remediation=(
                    "Add spark.kubernetes.node.selector.topology.kubernetes.io/zone=<az> "
                    "to your spark_conf, where <az> matches the AZ of your S3 Express bucket. "
                    "See docs/decisions/adr-004-s3-express-guidance.md for the full golden-path preset."
                ),
            )

    # Policy engine evaluation (#39)
    _add_policy_engine_checks(
        environment=environment,
        spark_conf=spark_conf,
        run=_run_obj,
        db=db,
        add_check=add_check,
    )

    # Lake Formation FGAC checks (#38)
    from sparkpilot.services.lake_formation import _add_lake_formation_fgac_checks
    _add_lake_formation_fgac_checks(
        environment=environment,
        db=db,
        add_check=add_check,
    )

    ready = all(item["status"] != "fail" for item in checks)
    return {
        "environment_id": environment.id,
        "run_id": run_id,
        "ready": ready,
        "generated_at": _now(),
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# TTL-cached wrapper for scheduler hot path
# ---------------------------------------------------------------------------

def _build_preflight_cached(
    environment: Environment,
    run_id: str | None = None,
    *,
    spark_conf: dict[str, str] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """TTL-cached wrapper around _build_preflight for scheduler hot path.

    Environment-level checks (AWS, release, budget) are cached for
    ``_PREFLIGHT_CACHE_TTL_SECONDS``.  Run-level checks always run fresh.
    """
    cache_key = _preflight_cache_key(environment, spark_conf)
    now = time.monotonic()
    with _preflight_cache_lock:
        _trim_preflight_cache(now)
        entry = _preflight_cache.get(cache_key)
        if entry is not None:
            cached_at, cached_result = entry
            if now - cached_at < _PREFLIGHT_CACHE_TTL_SECONDS:
                _preflight_cache.move_to_end(cache_key)
                # Return cached result with updated run_id / generated_at.
                result = dict(cached_result)
                result["run_id"] = run_id
                result["generated_at"] = _now()
                return result

    result = _build_preflight(environment, run_id=run_id, spark_conf=spark_conf, db=db)
    with _preflight_cache_lock:
        _trim_preflight_cache(now)
        _preflight_cache[cache_key] = (now, result)
        _preflight_cache.move_to_end(cache_key)
        _trim_preflight_cache(now)
    return result


# ---------------------------------------------------------------------------
# Preflight summary & audit helpers
# ---------------------------------------------------------------------------

def _preflight_summary(
    checks: list[dict[str, Any]],
    *,
    include_warnings: bool = False,
    include_remediation: bool = False,
) -> str:
    statuses = {"fail"}
    if include_warnings:
        statuses.add("warning")
    selected = []
    for item in checks:
        if item["status"] not in statuses:
            continue
        line = f"{item['code']}: {item['message']}"
        remediation = item.get("remediation")
        if include_remediation and remediation:
            line += f" Remediation: {remediation}"
        selected.append(line)
    return "; ".join(selected) if selected else "all checks passed"


def _has_preflight_audit(db: Session, run_id: str) -> bool:
    existing = db.execute(
        select(AuditEvent.id).where(
            and_(
                AuditEvent.entity_type == "run",
                AuditEvent.entity_id == run_id,
                AuditEvent.action.in_(PREFLIGHT_AUDIT_ACTIONS),
            )
        )
    ).first()
    return existing is not None
