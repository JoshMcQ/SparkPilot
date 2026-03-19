from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Callable

import pytest


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"Live integration disabled/missing env: {name}")
    return value


def require_live_tests_enabled() -> None:
    if os.getenv("SPARKPILOT_RUN_LIVE_TESTS", "0") != "1":
        pytest.skip("Set SPARKPILOT_RUN_LIVE_TESTS=1 to execute live AWS integration checks")


def build_live_byoc_env(issue_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"live-{issue_id}",
        engine="emr_on_eks",
        provisioning_mode="byoc_lite",
        status="ready",
        customer_role_arn=required_env("SPARKPILOT_LIVE_CUSTOMER_ROLE_ARN"),
        region=os.getenv("SPARKPILOT_LIVE_REGION", "us-east-1"),
        eks_cluster_arn=required_env("SPARKPILOT_LIVE_EKS_CLUSTER_ARN"),
        eks_namespace=required_env("SPARKPILOT_LIVE_EKS_NAMESPACE"),
        emr_virtual_cluster_id=os.getenv("SPARKPILOT_LIVE_EMR_VIRTUAL_CLUSTER_ID", "vc-live"),
    )


def make_check_collector() -> tuple[list[dict[str, object]], Callable[..., None]]:
    checks: list[dict[str, object]] = []

    def add_check(*, code: str, status_value: str, message: str, remediation: str | None = None, details=None):
        checks.append(
            {
                "code": code,
                "status": status_value,
                "message": message,
                "remediation": remediation,
                "details": details or {},
            }
        )

    return checks, add_check
