from pathlib import Path


TERRAFORM_ROOT = Path(__file__).parents[1] / "infra/terraform/control-plane"
MAIN_TF = (TERRAFORM_ROOT / "main.tf").read_text()
VARIABLES_TF = (TERRAFORM_ROOT / "variables.tf").read_text()


def test_ui_runtime_api_base_defaults_to_private_service_discovery() -> None:
    assert 'resource "aws_service_discovery_private_dns_namespace" "control_plane"' in MAIN_TF
    assert 'resource "aws_service_discovery_service" "api"' in MAIN_TF
    assert 'api_service_discovery_dns_name   = "api.${local.service_discovery_namespace_name}"' in MAIN_TF
    assert (
        'ui_runtime_api_base_url          = trimspace(var.ui_api_base_url) != "" '
        '? trimspace(var.ui_api_base_url) '
        ': "http://${local.api_service_discovery_dns_name}:8000"'
    ) in MAIN_TF
    assert '{ name = "SPARKPILOT_API", value = local.ui_runtime_api_base_url }' in MAIN_TF
    assert "private Cloud Map service discovery for UI-to-API traffic" in VARIABLES_TF


def test_ecs_tasks_allow_private_ui_to_api_traffic() -> None:
    assert 'resource "aws_vpc_security_group_ingress_rule" "ecs_api_from_ecs_tasks"' in MAIN_TF
    assert "security_group_id            = aws_security_group.ecs_tasks.id" in MAIN_TF
    assert "referenced_security_group_id = aws_security_group.ecs_tasks.id" in MAIN_TF
    assert 'description                  = "Allow private UI-to-API traffic between ECS tasks"' in MAIN_TF


def test_sparkpilot_api_does_not_reference_public_alb_or_dead_host() -> None:
    # Guard against silent drift back to the public ALB or the retired api.sparkpilot.cloud host.
    # Either would cause the UI ECS task to fail reaching the API from within the VPC.
    assert "api.sparkpilot.cloud" not in MAIN_TF
    # The SPARKPILOT_API assignment must use the local, not the ALB DNS output.
    sparkpilot_api_line = next(
        line for line in MAIN_TF.splitlines() if "SPARKPILOT_API" in line and "value" in line
    )
    assert "aws_lb" not in sparkpilot_api_line
