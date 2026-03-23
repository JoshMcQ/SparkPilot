from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from sparkpilot.aws_clients import EmrEksClient
from sparkpilot.config import get_settings
from tests._helpers import live_env_required as _required


def test_issue20_live_trust_policy_automation_real_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.getenv("SPARKPILOT_RUN_LIVE_TESTS", "0") != "1":
        pytest.skip("Set SPARKPILOT_RUN_LIVE_TESTS=1 to execute live AWS integration checks")

    # Require the EMR execution role ARN — no silent fallback to a hardcoded real
    # account ARN. A missing env var means the test is not configured, not that it
    # should silently run against a production account.
    emr_execution_role_arn = _required("SPARKPILOT_LIVE_EMR_EXECUTION_ROLE_ARN")

    # monkeypatch.setenv restores the original value (or removes the key) after the
    # test automatically, preventing env var state from leaking into subsequent tests.
    monkeypatch.setenv("SPARKPILOT_EMR_EXECUTION_ROLE_ARN", emr_execution_role_arn)
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
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
    role_name = str(update_result.get("role_name") or "").strip()
    provider_arn = str(update_result.get("provider_arn") or "").strip()
    trust_role_name = str(trust_result.get("role_name") or "").strip()
    trust_provider_arn = str(trust_result.get("provider_arn") or "").strip()
    assert role_name, "role_name should be non-empty"
    assert provider_arn, "provider_arn should be non-empty"
    assert trust_role_name, "trust_result.role_name should be non-empty"
    assert trust_provider_arn, "trust_result.provider_arn should be non-empty"

    get_settings.cache_clear()
