from __future__ import annotations

from sparkpilot.services.preflight_byoc import _add_byoc_lite_configuration_checks
from tests.live_preflight_test_utils import build_live_byoc_env, make_check_collector, require_live_tests_enabled


def test_issue19_live_namespace_checks_real_aws() -> None:
    require_live_tests_enabled()
    env = build_live_byoc_env("issue19")
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

    for code in [
        "byoc_lite.eks_namespace",
        "byoc_lite.eks_namespace_normalized",
        "byoc_lite.eks_namespace_format",
        "byoc_lite.namespace_bootstrap",
        "byoc_lite.namespace_collision",
    ]:
        assert code in by_code, f"Missing required namespace check: {code}"

    assert by_code["byoc_lite.eks_namespace"]["status"] == "pass"
    assert by_code["byoc_lite.eks_namespace_normalized"]["status"] == "pass"
    assert by_code["byoc_lite.eks_namespace_format"]["status"] == "pass"
    assert by_code["byoc_lite.namespace_bootstrap"]["status"] == "pass"

    collision_status = str(by_code["byoc_lite.namespace_collision"]["status"])
    assert collision_status in {"pass", "fail"}
    if collision_status == "fail":
        remediation = str(by_code["byoc_lite.namespace_collision"].get("remediation") or "")
        assert "delete-virtual-cluster" in remediation
