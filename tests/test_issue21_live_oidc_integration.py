from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from sparkpilot.aws_clients import EmrEksClient
from sparkpilot.config import get_settings
from tests._helpers import live_env_required as _required


def test_issue21_live_oidc_detection_real_aws() -> None:
    if os.getenv("SPARKPILOT_RUN_LIVE_TESTS", "0") != "1":
        pytest.skip("Set SPARKPILOT_RUN_LIVE_TESTS=1 to execute live AWS integration checks")

    os.environ["SPARKPILOT_DRY_RUN_MODE"] = "false"
    get_settings.cache_clear()
    if get_settings().dry_run_mode:
        pytest.skip("SPARKPILOT_DRY_RUN_MODE must be false for live OIDC detection validation")

    env = SimpleNamespace(
        customer_role_arn=_required("SPARKPILOT_LIVE_CUSTOMER_ROLE_ARN"),
        region=os.getenv("SPARKPILOT_LIVE_REGION", "us-east-1"),
        eks_cluster_arn=_required("SPARKPILOT_LIVE_EKS_CLUSTER_ARN"),
        eks_namespace=_required("SPARKPILOT_LIVE_EKS_NAMESPACE"),
    )

    result = EmrEksClient().check_oidc_provider_association(env)
    assert result["associated"] is True
    cluster_name = str(result.get("cluster_name") or "").strip()
    oidc_provider_arn = str(result.get("oidc_provider_arn") or "").strip()
    assert cluster_name, "cluster_name should be non-empty"
    assert oidc_provider_arn, "oidc_provider_arn should be non-empty"

    get_settings.cache_clear()
