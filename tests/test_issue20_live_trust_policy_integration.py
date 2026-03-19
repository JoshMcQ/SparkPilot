from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from sparkpilot.aws_clients import EmrEksClient
from sparkpilot.config import get_settings


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"Live integration disabled/missing env: {name}")
    return value


def test_issue20_live_trust_policy_automation_real_aws() -> None:
    if os.getenv("SPARKPILOT_RUN_LIVE_TESTS", "0") != "1":
        pytest.skip("Set SPARKPILOT_RUN_LIVE_TESTS=1 to execute live AWS integration checks")

    os.environ["SPARKPILOT_DRY_RUN_MODE"] = "false"
    get_settings.cache_clear()
    if get_settings().dry_run_mode:
        pytest.skip("SPARKPILOT_DRY_RUN_MODE must be false for live trust-policy automation validation")

    env = SimpleNamespace(
        engine="emr_on_eks",
        provisioning_mode="byoc_lite",
        customer_role_arn=_required("SPARKPILOT_LIVE_CUSTOMER_ROLE_ARN"),
        region=os.getenv("SPARKPILOT_LIVE_REGION", "us-east-1"),
        eks_cluster_arn=_required("SPARKPILOT_LIVE_EKS_CLUSTER_ARN"),
        eks_namespace=_required("SPARKPILOT_LIVE_EKS_NAMESPACE"),
    )

    client = EmrEksClient()
    update_result = client.update_execution_role_trust_policy(env)
    trust_result = client.check_execution_role_trust_policy(env)

    assert bool(update_result.get("updated")) is True
    assert bool(update_result.get("already_present")) in {True, False}
    assert str(update_result.get("role_name") or "")
    assert str(update_result.get("provider_arn") or "")
    assert str(trust_result.get("role_name") or "")
    assert str(trust_result.get("provider_arn") or "")

    get_settings.cache_clear()
