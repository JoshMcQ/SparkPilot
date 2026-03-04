from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
import subprocess

from sparkpilot.config import get_settings
from sparkpilot.models import Environment, ProvisioningOperation


REPO_ROOT = Path(__file__).resolve().parents[2]
FULL_BYOC_TERRAFORM_ROOT = REPO_ROOT / "infra" / "terraform" / "full-byoc"
FULL_BYOC_STATE_PREFIX = "sparkpilot/full-byoc"


@dataclass(frozen=True)
class ProvisioningStageContext:
    operation_id: str
    environment_id: str
    tenant_id: str
    stage: str
    region: str
    workspace: str
    state_key: str
    working_dir: Path
    attempt: int = 1
    var_overrides: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TerraformPlanResult:
    ok: bool
    command: list[str]
    plan_path: str | None
    stdout_excerpt: str
    stderr_excerpt: str
    error: str | None = None


@dataclass(frozen=True)
class TerraformApplyResult:
    ok: bool
    command: list[str]
    stdout_excerpt: str
    stderr_excerpt: str
    error: str | None = None
    outputs: dict[str, str] = field(default_factory=dict)


class TerraformOrchestrator:
    def __init__(
        self,
        *,
        terraform_binary: str = "terraform",
        enable_subprocess: bool | None = None,
        timeout_seconds: int = 900,
    ) -> None:
        settings = get_settings()
        self.terraform_binary = terraform_binary
        self.enable_subprocess = (not settings.dry_run_mode) if enable_subprocess is None else enable_subprocess
        self.timeout_seconds = timeout_seconds

    def build_stage_context(
        self,
        operation: ProvisioningOperation,
        environment: Environment,
        stage: str,
        *,
        attempt: int,
    ) -> ProvisioningStageContext:
        workspace = f"sp-{environment.tenant_id[:8]}-{environment.id[:8]}"
        state_key = f"{FULL_BYOC_STATE_PREFIX}/{environment.tenant_id}/{environment.id}/terraform.tfstate"
        var_overrides = {
            "tenant_id": environment.tenant_id,
            "environment_id": environment.id,
            "region": environment.region,
            "stage": stage,
            "workspace": workspace,
            "state_key": state_key,
        }
        return ProvisioningStageContext(
            operation_id=operation.id,
            environment_id=environment.id,
            tenant_id=environment.tenant_id,
            stage=stage,
            region=environment.region,
            workspace=workspace,
            state_key=state_key,
            working_dir=FULL_BYOC_TERRAFORM_ROOT,
            attempt=attempt,
            var_overrides=var_overrides,
        )

    def plan(self, context: ProvisioningStageContext) -> TerraformPlanResult:
        plan_path = context.working_dir / f"{context.operation_id}-{context.stage}.tfplan"
        command = self._build_plan_command(context, plan_path)
        if not self.enable_subprocess:
            return TerraformPlanResult(
                ok=True,
                command=command,
                plan_path=str(plan_path),
                stdout_excerpt="dry-run terraform plan",
                stderr_excerpt="",
            )

        self._validate_runtime_prerequisites(context)
        completed = self._run(command, cwd=context.working_dir)
        return TerraformPlanResult(
            ok=completed.returncode == 0,
            command=command,
            plan_path=str(plan_path),
            stdout_excerpt=self._excerpt(completed.stdout),
            stderr_excerpt=self._excerpt(completed.stderr),
            error=None if completed.returncode == 0 else "terraform plan failed",
        )

    def apply(
        self,
        context: ProvisioningStageContext,
        plan_result: TerraformPlanResult,
    ) -> TerraformApplyResult:
        plan_path = plan_result.plan_path or str(
            context.working_dir / f"{context.operation_id}-{context.stage}.tfplan"
        )
        command = [
            self.terraform_binary,
            "apply",
            "-input=false",
            "-no-color",
            "-auto-approve",
            plan_path,
        ]
        if not self.enable_subprocess:
            return TerraformApplyResult(
                ok=True,
                command=command,
                stdout_excerpt="dry-run terraform apply",
                stderr_excerpt="",
                outputs={},
            )

        self._validate_runtime_prerequisites(context)
        completed = self._run(command, cwd=context.working_dir)
        return TerraformApplyResult(
            ok=completed.returncode == 0,
            command=command,
            stdout_excerpt=self._excerpt(completed.stdout),
            stderr_excerpt=self._excerpt(completed.stderr),
            error=None if completed.returncode == 0 else "terraform apply failed",
            outputs={},
        )

    def _build_plan_command(self, context: ProvisioningStageContext, plan_path: Path) -> list[str]:
        command = [
            self.terraform_binary,
            "plan",
            "-input=false",
            "-no-color",
            "-out",
            str(plan_path),
        ]
        for key, value in sorted(context.var_overrides.items()):
            command.extend(["-var", f"{key}={value}"])
        return command

    def _validate_runtime_prerequisites(self, context: ProvisioningStageContext) -> None:
        if shutil.which(self.terraform_binary) is None:
            raise ValueError(
                f"Terraform binary '{self.terraform_binary}' was not found on PATH. "
                "Install Terraform or configure provisioning runner image with Terraform."
            )
        if not context.working_dir.exists():
            raise ValueError(
                f"Terraform working directory '{context.working_dir}' does not exist. "
                "Add full-BYOC Terraform modules before enabling live full-mode provisioning."
            )

    def _run(self, command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ValueError(f"Terraform command failed to start: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError(
                f"Terraform command timed out after {self.timeout_seconds} seconds: {' '.join(command)}"
            ) from exc

    def _excerpt(self, value: str, *, limit: int = 2000) -> str:
        text = value.strip()
        if len(text) <= limit:
            return text
        return text[:limit] + "...[truncated]"
