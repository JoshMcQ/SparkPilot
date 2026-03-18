from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from sparkpilot.terraform_orchestrator import (
    ProvisioningStageContext,
    TerraformApplyResult,
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


def _context_with_overrides(
    tmp_path: Path,
    stage: str = "provisioning_network",
    var_overrides: dict[str, str] | None = None,
) -> ProvisioningStageContext:
    """Build a context with explicit var_overrides for assertion tests."""
    overrides = var_overrides or {"region": "us-east-1", "stage": stage}
    return ProvisioningStageContext(
        operation_id="op-abc",
        environment_id="env-abc",
        tenant_id="tenant-abc",
        stage=stage,
        region="us-east-1",
        workspace="sp-tenantab-envabcde",
        state_key="sparkpilot/full-byoc/tenant-abc/env-abc/terraform.tfstate",
        working_dir=tmp_path,
        attempt=1,
        var_overrides=overrides,
    )


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    result: subprocess.CompletedProcess[str] = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


# ---------------------------------------------------------------------------
# Existing tests (retained)
# ---------------------------------------------------------------------------


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


def test_terraform_apply_result_outputs_default_is_empty_dict() -> None:
    """Regression: TerraformApplyResult.outputs must default to {} not None."""
    result = TerraformApplyResult(
        ok=True,
        command=["terraform", "apply"],
        stdout_excerpt="",
        stderr_excerpt="",
    )
    assert result.outputs == {}, "outputs default must be an empty dict, not None or missing"
    assert isinstance(result.outputs, dict)


def test_terraform_orchestrator_reports_missing_binary(tmp_path: Path) -> None:
    context = _context(tmp_path)
    orchestrator = TerraformOrchestrator(
        terraform_binary="terraform-not-installed-for-test",
        enable_subprocess=True,
    )

    with pytest.raises(ValueError) as exc_info:
        orchestrator.plan(context)
    assert "not found on PATH" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TASK 2 – New tests
# ---------------------------------------------------------------------------


class TestVarInjection:
    """Verify that customer_role_arn and eks_namespace appear in -var args."""

    def test_customer_role_arn_is_injected_into_plan_command(self, tmp_path: Path) -> None:
        overrides = {
            "region": "us-east-1",
            "stage": "provisioning_network",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomer",
        }
        context = _context_with_overrides(tmp_path, var_overrides=overrides)
        orchestrator = TerraformOrchestrator(enable_subprocess=False)

        plan_result = orchestrator.plan(context)
        command_str = " ".join(plan_result.command)

        assert "-var" in plan_result.command
        assert "customer_role_arn=arn:aws:iam::123456789012:role/SparkPilotCustomer" in command_str

    def test_eks_namespace_is_injected_into_plan_command_when_present(self, tmp_path: Path) -> None:
        overrides = {
            "region": "us-east-1",
            "stage": "provisioning_emr",
            "customer_role_arn": "arn:aws:iam::111111111111:role/Role",
            "eks_namespace": "my-spark-ns",
        }
        context = _context_with_overrides(tmp_path, stage="provisioning_emr", var_overrides=overrides)
        orchestrator = TerraformOrchestrator(enable_subprocess=False)

        plan_result = orchestrator.plan(context)
        command_str = " ".join(plan_result.command)

        assert "eks_namespace=my-spark-ns" in command_str

    def test_eks_namespace_absent_when_not_in_overrides(self, tmp_path: Path) -> None:
        overrides = {
            "region": "us-east-1",
            "stage": "provisioning_network",
            "customer_role_arn": "arn:aws:iam::111111111111:role/Role",
        }
        context = _context_with_overrides(tmp_path, var_overrides=overrides)
        orchestrator = TerraformOrchestrator(enable_subprocess=False)

        plan_result = orchestrator.plan(context)
        command = plan_result.command

        # Collect keys injected via -var to avoid false positives from the tmp_path
        var_keys: list[str] = []
        for i, item in enumerate(command):
            if item == "-var" and i + 1 < len(command):
                k, _, _ = command[i + 1].partition("=")
                var_keys.append(k)

        assert "eks_namespace" not in var_keys

    def test_build_stage_context_injects_customer_role_arn_and_eks_namespace(self, tmp_path: Path) -> None:
        """build_stage_context should put customer_role_arn and eks_namespace in var_overrides."""
        from sparkpilot.models import Environment, ProvisioningOperation

        env = Environment(
            id="env-xyz",
            tenant_id="tenant-xyz",
            region="us-west-2",
            customer_role_arn="arn:aws:iam::999999999999:role/SparkPilotRole",
            eks_namespace="custom-namespace",
        )
        op = ProvisioningOperation(
            id="op-xyz",
            environment_id="env-xyz",
            idempotency_key="idem-key-xyz",
        )

        orchestrator = TerraformOrchestrator(enable_subprocess=False)
        ctx = orchestrator.build_stage_context(op, env, "provisioning_emr", attempt=1)

        assert ctx.var_overrides["customer_role_arn"] == "arn:aws:iam::999999999999:role/SparkPilotRole"
        assert ctx.var_overrides["eks_namespace"] == "custom-namespace"

    def test_build_stage_context_omits_eks_namespace_when_not_set(self, tmp_path: Path) -> None:
        """eks_namespace should not appear in var_overrides if the Environment has no namespace."""
        from sparkpilot.models import Environment, ProvisioningOperation

        env = Environment(
            id="env-nons",
            tenant_id="tenant-nons",
            region="us-east-1",
            customer_role_arn="arn:aws:iam::111111111111:role/Role",
            eks_namespace=None,
        )
        op = ProvisioningOperation(
            id="op-nons",
            environment_id="env-nons",
            idempotency_key="idem-key-nons",
        )

        orchestrator = TerraformOrchestrator(enable_subprocess=False)
        ctx = orchestrator.build_stage_context(op, env, "provisioning_network", attempt=1)

        assert "eks_namespace" not in ctx.var_overrides

    def test_var_flags_appear_as_separate_list_elements(self, tmp_path: Path) -> None:
        """Each -var key=value pair must be two list items: ['-var', 'key=value']."""
        overrides = {
            "customer_role_arn": "arn:aws:iam::123:role/R",
            "region": "eu-west-1",
            "stage": "provisioning_network",
        }
        context = _context_with_overrides(tmp_path, var_overrides=overrides)
        orchestrator = TerraformOrchestrator(enable_subprocess=False)

        plan_result = orchestrator.plan(context)
        command = plan_result.command

        # Each -var must be immediately followed by key=value
        var_pairs: dict[str, str] = {}
        for i, item in enumerate(command):
            if item == "-var" and i + 1 < len(command):
                k, _, v = command[i + 1].partition("=")
                var_pairs[k] = v

        assert var_pairs.get("customer_role_arn") == "arn:aws:iam::123:role/R"
        assert var_pairs.get("region") == "eu-west-1"


class TestInitAndWorkspaceIdempotency:
    """Verify that terraform init and workspace are called exactly once per workspace."""

    def _make_run_side_effects(self, workspace: str) -> list[subprocess.CompletedProcess[str]]:
        """
        Return side-effect list for _run calls in _ensure_initialized:
          1. terraform init -> success
          2. terraform workspace select -> success (workspace exists)
        Then for plan:
          3. terraform plan -> success
        """
        return [
            _completed(0, "Terraform initialized"),   # init
            _completed(0),                             # workspace select
            _completed(0, "Plan: 0 to add"),           # plan
        ]

    def test_init_called_only_once_for_same_workspace(self, tmp_path: Path) -> None:
        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _completed(0, "Terraform initialized"),  # init
                _completed(0),                            # workspace select
                _completed(0, "Plan: 0 to add"),          # plan (first call)
                _completed(0, "Plan: 0 to add"),          # plan (second call)
            ]

            plan_path_1 = str(tmp_path / f"{context.operation_id}-{context.stage}.tfplan")
            orchestrator.plan(context)
            orchestrator.plan(context)

        calls = mock_run.call_args_list
        # Collect the sub-commands
        subcmds = [c.args[0][1] for c in calls]  # second element is the subcommand
        assert subcmds.count("init") == 1, "terraform init must be called exactly once per workspace"

    def test_workspace_setup_called_only_once_for_same_workspace(self, tmp_path: Path) -> None:
        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _completed(0, "Terraform initialized"),  # init
                _completed(0),                            # workspace select
                _completed(0, "Plan: 0 to add"),          # plan call 1
                _completed(0, "Plan: 0 to add"),          # plan call 2
            ]

            orchestrator.plan(context)
            orchestrator.plan(context)

        calls = mock_run.call_args_list
        subcmds = [c.args[0][1] for c in calls]
        assert subcmds.count("workspace") == 1, "terraform workspace must be called exactly once per workspace"

    def test_init_called_again_for_different_workspace(self, tmp_path: Path) -> None:
        """Different workspaces must each trigger their own init."""
        ctx1 = ProvisioningStageContext(
            operation_id="op-111",
            environment_id="env-111",
            tenant_id="t1",
            stage="provisioning_network",
            region="us-east-1",
            workspace="ws-one",
            state_key="key1",
            working_dir=tmp_path,
            attempt=1,
            var_overrides={"stage": "provisioning_network"},
        )
        ctx2 = ProvisioningStageContext(
            operation_id="op-222",
            environment_id="env-222",
            tenant_id="t2",
            stage="provisioning_network",
            region="us-east-1",
            workspace="ws-two",
            state_key="key2",
            working_dir=tmp_path,
            attempt=1,
            var_overrides={"stage": "provisioning_network"},
        )
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _completed(0, "Terraform initialized"),  # init for ws-one
                _completed(0),                            # workspace select ws-one
                _completed(0, "Plan: 0 to add"),          # plan for ctx1
                _completed(0, "Terraform initialized"),  # init for ws-two
                _completed(0),                            # workspace select ws-two
                _completed(0, "Plan: 0 to add"),          # plan for ctx2
            ]

            orchestrator.plan(ctx1)
            orchestrator.plan(ctx2)

        calls = mock_run.call_args_list
        subcmds = [c.args[0][1] for c in calls]
        assert subcmds.count("init") == 2, "each distinct workspace should trigger its own init"


class TestBackendEnvVars:
    """Backend env vars should alter the terraform init -backend-config= args."""

    def test_backend_config_args_added_when_bucket_env_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPARKPILOT_TERRAFORM_STATE_BUCKET", "my-tf-state-bucket")
        monkeypatch.setenv("SPARKPILOT_TERRAFORM_STATE_REGION", "us-east-1")
        monkeypatch.delenv("SPARKPILOT_TERRAFORM_STATE_LOCK_TABLE", raising=False)
        monkeypatch.delenv("SPARKPILOT_TERRAFORM_STATE_ROLE_ARN", raising=False)

        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _completed(0, "Terraform initialized"),
                _completed(0),
                _completed(0, "Plan: 0 to add"),
            ]
            orchestrator.plan(context)

        init_call = mock_run.call_args_list[0]
        init_cmd = init_call.args[0]
        init_str = " ".join(init_cmd)

        assert "-backend-config" in init_cmd
        assert "bucket=my-tf-state-bucket" in init_str
        assert "key=sparkpilot/full-byoc/tenant-123/env-123/terraform.tfstate" in init_str
        assert "region=us-east-1" in init_str
        assert "-backend=false" not in init_cmd

    def test_backend_false_used_when_no_bucket_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SPARKPILOT_TERRAFORM_STATE_BUCKET", raising=False)

        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _completed(0, "Terraform initialized"),
                _completed(0),
                _completed(0, "Plan: 0 to add"),
            ]
            orchestrator.plan(context)

        init_call = mock_run.call_args_list[0]
        init_cmd = init_call.args[0]

        assert "-backend=false" in init_cmd
        assert "-backend-config" not in init_cmd

    def test_dynamodb_table_added_to_backend_config_when_env_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPARKPILOT_TERRAFORM_STATE_BUCKET", "lock-bucket")
        monkeypatch.setenv("SPARKPILOT_TERRAFORM_STATE_REGION", "eu-west-1")
        monkeypatch.setenv("SPARKPILOT_TERRAFORM_STATE_LOCK_TABLE", "tf-locks")
        monkeypatch.delenv("SPARKPILOT_TERRAFORM_STATE_ROLE_ARN", raising=False)

        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _completed(0, "Terraform initialized"),
                _completed(0),
                _completed(0, "Plan: 0 to add"),
            ]
            orchestrator.plan(context)

        init_cmd = " ".join(mock_run.call_args_list[0].args[0])
        assert "dynamodb_table=tf-locks" in init_cmd

    def test_dynamodb_table_absent_when_env_not_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPARKPILOT_TERRAFORM_STATE_BUCKET", "lock-bucket")
        monkeypatch.setenv("SPARKPILOT_TERRAFORM_STATE_REGION", "eu-west-1")
        monkeypatch.delenv("SPARKPILOT_TERRAFORM_STATE_LOCK_TABLE", raising=False)
        monkeypatch.delenv("SPARKPILOT_TERRAFORM_STATE_ROLE_ARN", raising=False)

        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _completed(0, "Terraform initialized"),
                _completed(0),
                _completed(0, "Plan: 0 to add"),
            ]
            orchestrator.plan(context)

        init_cmd = " ".join(mock_run.call_args_list[0].args[0])
        assert "dynamodb_table" not in init_cmd

    def test_role_arn_added_to_backend_config_when_env_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPARKPILOT_TERRAFORM_STATE_BUCKET", "some-bucket")
        monkeypatch.setenv("SPARKPILOT_TERRAFORM_STATE_REGION", "us-west-2")
        monkeypatch.delenv("SPARKPILOT_TERRAFORM_STATE_LOCK_TABLE", raising=False)
        monkeypatch.setenv("SPARKPILOT_TERRAFORM_STATE_ROLE_ARN", "arn:aws:iam::123:role/TFState")

        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _completed(0, "Terraform initialized"),
                _completed(0),
                _completed(0, "Plan: 0 to add"),
            ]
            orchestrator.plan(context)

        init_cmd = " ".join(mock_run.call_args_list[0].args[0])
        assert "role_arn=arn:aws:iam::123:role/TFState" in init_cmd


class TestInitAndWorkspaceErrorMessages:
    """Failures in init or workspace should surface actionable error messages."""

    def test_init_failure_raises_actionable_value_error(self, tmp_path: Path) -> None:
        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _completed(1, stderr="Error: Backend configuration changed"),
            ]

            with pytest.raises(ValueError) as exc_info:
                orchestrator.plan(context)

        msg = str(exc_info.value)
        assert "Terraform init failed" in msg
        assert "Backend configuration changed" in msg

    def test_init_failure_message_includes_stdout_when_stderr_empty(self, tmp_path: Path) -> None:
        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _completed(1, stdout="No valid credential sources found", stderr=""),
            ]

            with pytest.raises(ValueError) as exc_info:
                orchestrator.plan(context)

        msg = str(exc_info.value)
        assert "Terraform init failed" in msg
        assert "No valid credential sources found" in msg

    def test_workspace_create_failure_raises_actionable_value_error(self, tmp_path: Path) -> None:
        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run") as mock_run:
            # init succeeds, workspace select fails, workspace new fails
            mock_run.side_effect = [
                _completed(0, "Terraform initialized"),
                _completed(1, stderr="Workspace does not exist"),
                _completed(1, stderr="Error creating workspace: permission denied"),
            ]

            with pytest.raises(ValueError) as exc_info:
                orchestrator.plan(context)

        msg = str(exc_info.value)
        assert "Terraform workspace setup failed" in msg
        assert "permission denied" in msg

    def test_workspace_create_failure_not_generic_exception(self, tmp_path: Path) -> None:
        """The raised exception must be a ValueError, not a raw RuntimeError or Exception."""
        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _completed(0, "Terraform initialized"),
                _completed(1, stderr="no such workspace"),
                _completed(1, stderr="workspace creation failed"),
            ]

            with pytest.raises(ValueError):
                orchestrator.plan(context)

    def test_init_failure_is_value_error_not_generic(self, tmp_path: Path) -> None:
        """Init failure must raise ValueError (actionable), not bare Exception or RuntimeError."""
        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _completed(1, stderr="could not connect to backend"),
            ]

            with pytest.raises(ValueError):
                orchestrator.plan(context)

    def test_command_not_found_raises_value_error_with_context(self, tmp_path: Path) -> None:
        """FileNotFoundError from subprocess should be wrapped in a ValueError."""
        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run", side_effect=FileNotFoundError("terraform: not found")):
            with pytest.raises(ValueError) as exc_info:
                orchestrator.plan(context)

        assert "Terraform command failed to start" in str(exc_info.value)

    def test_timeout_raises_value_error_with_duration(self, tmp_path: Path) -> None:
        """TimeoutExpired should be wrapped in ValueError mentioning timeout duration."""
        context = _context(tmp_path)
        orchestrator = TerraformOrchestrator(
            terraform_binary="terraform",
            enable_subprocess=True,
            timeout_seconds=30,
        )

        with patch("shutil.which", return_value="/usr/bin/terraform"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["terraform"], timeout=30)):
            with pytest.raises(ValueError) as exc_info:
                orchestrator.plan(context)

        assert "timed out" in str(exc_info.value).lower()
        assert "30" in str(exc_info.value)
