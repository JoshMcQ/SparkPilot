from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from sparkpilot.services.preflight_checks import _add_issue3_dispatch_gate_checks


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"Live integration disabled/missing env: {name}")
    return value


def test_issue3_live_preflight_checks_real_aws() -> None:
    if os.getenv("SPARKPILOT_RUN_LIVE_TESTS", "0") != "1":
        pytest.skip("Set SPARKPILOT_RUN_LIVE_TESTS=1 to execute live AWS integration checks")

    env = SimpleNamespace(
        engine="emr_on_eks",
        provisioning_mode="byoc_lite",
        customer_role_arn=_required("SPARKPILOT_LIVE_CUSTOMER_ROLE_ARN"),
        region=os.getenv("SPARKPILOT_LIVE_REGION", "us-east-1"),
        eks_cluster_arn=_required("SPARKPILOT_LIVE_EKS_CLUSTER_ARN"),
        eks_namespace=_required("SPARKPILOT_LIVE_EKS_NAMESPACE"),
    )

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

    _add_issue3_dispatch_gate_checks(environment=env, add_check=add_check)

    codes = [row["code"] for row in checks]
    assert codes == [
        "issue3.sts_caller_identity",
        "issue3.iam_simulate_principal_policy",
        "issue3.eks_describe_cluster",
        "issue3.irsa_trust_subject",
    ]

    failed = [row for row in checks if row["status"] == "fail"]
    assert failed == [], f"Live preflight checks failed: {failed}"
