from __future__ import annotations

from sparkpilot.services.preflight_byoc import _add_byoc_lite_configuration_checks
from tests.live_preflight_test_utils import build_live_byoc_env, make_check_collector, require_live_tests_enabled


def test_issue18_live_byoc_lite_prerequisites_real_aws() -> None:
    require_live_tests_enabled()
    env = build_live_byoc_env("issue18")
    checks, add_check = make_check_collector()

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
