from pathlib import Path

import pytest

from sparkpilot.terraform_orchestrator import (
    ProvisioningStageContext,
    TerraformOrchestrator,
)


def _context(tmp_path: Path, stage: str = "provisioning_network") -> ProvisioningStageContext:
    return ProvisioningStageContext(
        operation_id="op-123",
        environment_id="env-123",
        tenant_id="tenant-123",
        stage=stage,
        region="us-east-1",
        workspace="sp-tenant-e2e",
        state_key="sparkpilot/full-byoc/tenant-123/env-123/terraform.tfstate",
        working_dir=tmp_path,
        attempt=1,
        var_overrides={"region": "us-east-1", "stage": stage},
    )


def test_terraform_orchestrator_dry_run_plan_and_apply(tmp_path: Path) -> None:
    context = _context(tmp_path)
    orchestrator = TerraformOrchestrator(enable_subprocess=False)

    plan_result = orchestrator.plan(context)
    assert plan_result.ok is True
    assert plan_result.plan_path is not None
    assert "plan" in plan_result.command

    apply_result = orchestrator.apply(context, plan_result)
    assert apply_result.ok is True
    assert "apply" in apply_result.command
    assert apply_result.outputs == {}


def test_terraform_orchestrator_reports_missing_binary(tmp_path: Path) -> None:
    context = _context(tmp_path)
    orchestrator = TerraformOrchestrator(
        terraform_binary="terraform-not-installed-for-test",
        enable_subprocess=True,
    )

    with pytest.raises(ValueError) as exc_info:
        orchestrator.plan(context)
    assert "not found on PATH" in str(exc_info.value)
