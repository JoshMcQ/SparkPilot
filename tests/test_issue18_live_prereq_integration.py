from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from sparkpilot.services.preflight_byoc import _add_byoc_lite_configuration_checks


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"Live integration disabled/missing env: {name}")
    return value


def test_issue18_live_byoc_lite_prerequisites_real_aws() -> None:
    if os.getenv("SPARKPILOT_RUN_LIVE_TESTS", "0") != "1":
        pytest.skip("Set SPARKPILOT_RUN_LIVE_TESTS=1 to execute live AWS integration checks")

    env = SimpleNamespace(
        id="live-issue18",
        engine="emr_on_eks",
        provisioning_mode="byoc_lite",
        status="ready",
        customer_role_arn=_required("SPARKPILOT_LIVE_CUSTOMER_ROLE_ARN"),
        region=os.getenv("SPARKPILOT_LIVE_REGION", "us-east-1"),
        eks_cluster_arn=_required("SPARKPILOT_LIVE_EKS_CLUSTER_ARN"),
        eks_namespace=_required("SPARKPILOT_LIVE_EKS_NAMESPACE"),
        emr_virtual_cluster_id=os.getenv("SPARKPILOT_LIVE_EMR_VIRTUAL_CLUSTER_ID", "vc-live"),
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

    _add_byoc_lite_configuration_checks(
        environment=env,
        spark_conf={
            "spark.kubernetes.executor.node.selector.eks.amazonaws.com/capacityType": "spot",
            "spark.kubernetes.executor.tolerations": "spot=true:PreferNoSchedule",
        },
        add_check=add_check,
    )

    by_code = {item["code"]: item for item in checks}
    required_codes = [
        "byoc_lite.eks_cluster_arn",
        "byoc_lite.eks_namespace",
        "byoc_lite.eks_namespace_format",
        "byoc_lite.namespace_bootstrap",
        "byoc_lite.eks_cluster_region",
        "byoc_lite.account_alignment",
        "byoc_lite.oidc_association",
        "byoc_lite.execution_role_trust",
        "byoc_lite.customer_role_dispatch",
        "byoc_lite.iam_pass_role",
    ]

    for code in required_codes:
        assert code in by_code, f"Missing required prerequisite check: {code}"

    hard_failures = [
        by_code[code]
        for code in required_codes
        if by_code[code]["status"] == "fail"
    ]
    assert hard_failures == [], f"Live prerequisites failed: {hard_failures}"

    failed_or_warning = [item for item in checks if item["status"] in {"fail", "warning"}]
    for item in failed_or_warning:
        # warnings may be informational, but if remediation exists it must be non-empty actionable text
        if item.get("remediation") is not None:
            assert str(item["remediation"]).strip(), f"Empty remediation for {item['code']}"
