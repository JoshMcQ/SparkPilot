terraform {
  required_version = ">= 1.7.0"

  # Remote state is required; configure bucket/key/region/table with -backend-config.
  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.95"
    }
  }
}

provider "aws" {
  region = var.region
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  tags = merge(var.default_tags, {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })

  is_dev_environment = contains(["dev", "development", "local", "test"], lower(var.environment))

  rds_deletion_protection_effective = var.rds_deletion_protection == null ? !local.is_dev_environment : var.rds_deletion_protection
  rds_skip_final_snapshot_effective = var.rds_skip_final_snapshot == null ? local.is_dev_environment : var.rds_skip_final_snapshot
  rds_final_snapshot_identifier_effective = local.rds_skip_final_snapshot_effective ? null : (
    trimspace(var.rds_final_snapshot_identifier) != "" ? trimspace(var.rds_final_snapshot_identifier) : "${local.name_prefix}-final"
  )
  cur_config_any = (
    trimspace(var.cur_athena_database) != "" ||
    trimspace(var.cur_athena_table) != "" ||
    trimspace(var.cur_athena_output_location) != ""
  )
  cur_config_complete = (
    trimspace(var.cur_athena_database) != "" &&
    trimspace(var.cur_athena_table) != "" &&
    trimspace(var.cur_athena_output_location) != ""
  )

  alb_subnet_ids = length(var.public_subnet_ids) > 0 ? var.public_subnet_ids : var.private_subnet_ids
  alb_internal   = length(var.public_subnet_ids) == 0
  db_url         = "postgresql+psycopg://${urlencode(var.db_username)}:${urlencode(var.db_password)}@${aws_db_instance.postgres.address}:5432/${var.db_name}"

  api_task_name = substr(replace("${local.name_prefix}-api", "_", "-"), 0, 32)
  api_tg_name   = substr(replace("${local.name_prefix}-api-tg", "_", "-"), 0, 32)
  alb_name      = substr(replace("${local.name_prefix}-alb", "_", "-"), 0, 32)

  allowed_fargate_memory_by_cpu = {
    "256"  = [512, 1024, 2048]
    "512"  = [1024, 2048, 3072, 4096]
    "1024" = [2048, 3072, 4096, 5120, 6144, 7168, 8192]
    "2048" = [for memory in range(4096, 16384 + 1024, 1024) : memory]
    "4096" = [for memory in range(8192, 30720 + 1024, 1024) : memory]
  }

  common_runtime_env = [
    { name = "SPARKPILOT_ENVIRONMENT", value = var.environment },
    { name = "SPARKPILOT_DATABASE_URL", value = local.db_url },
    { name = "SPARKPILOT_DRY_RUN_MODE", value = tostring(var.dry_run_mode) },
    { name = "SPARKPILOT_ENABLE_FULL_BYOC_MODE", value = tostring(var.enable_full_byoc_mode) },
    { name = "SPARKPILOT_AUTH_MODE", value = "oidc" },
    { name = "SPARKPILOT_OIDC_ISSUER", value = var.oidc_issuer },
    { name = "SPARKPILOT_OIDC_AUDIENCE", value = var.oidc_audience },
    { name = "SPARKPILOT_OIDC_JWKS_URI", value = var.oidc_jwks_uri },
    { name = "SPARKPILOT_BOOTSTRAP_SECRET", value = var.bootstrap_secret },
    { name = "SPARKPILOT_AWS_REGION", value = var.region },
    { name = "SPARKPILOT_POLL_INTERVAL_SECONDS", value = tostring(var.poll_interval_seconds) },
    { name = "SPARKPILOT_CORS_ORIGINS", value = join(",", var.cors_origins) },
    { name = "SPARKPILOT_EMR_EXECUTION_ROLE_ARN", value = var.emr_execution_role_arn },
    { name = "SPARKPILOT_CUR_ATHENA_DATABASE", value = var.cur_athena_database },
    { name = "SPARKPILOT_CUR_ATHENA_TABLE", value = var.cur_athena_table },
    { name = "SPARKPILOT_CUR_ATHENA_WORKGROUP", value = var.cur_athena_workgroup },
    { name = "SPARKPILOT_CUR_ATHENA_OUTPUT_LOCATION", value = var.cur_athena_output_location },
    { name = "SPARKPILOT_CUR_RUN_ID_COLUMN", value = var.cur_run_id_column },
    { name = "SPARKPILOT_CUR_COST_COLUMN", value = var.cur_cost_column },
    { name = "SPARKPILOT_COST_CENTER_POLICY_JSON", value = var.cost_center_policy_json },
  ]

  worker_specs = {
    provisioner = ["python", "-m", "sparkpilot.workers", "provisioner"]
    scheduler   = ["python", "-m", "sparkpilot.workers", "scheduler"]
    reconciler  = ["python", "-m", "sparkpilot.workers", "reconciler"]
  }
}

check "emr_execution_role_required_in_live_mode" {
  assert {
    condition = var.dry_run_mode || (
      trimspace(var.emr_execution_role_arn) != "" &&
      !startswith(var.emr_execution_role_arn, "arn:aws:iam::111111111111:")
    )
    error_message = "When dry_run_mode=false, emr_execution_role_arn must be set to a real IAM role ARN."
  }
}

check "fargate_cpu_memory_valid_for_api" {
  assert {
    condition = contains(
      local.allowed_fargate_memory_by_cpu[tostring(var.api_task_cpu)],
      var.api_task_memory,
    )
    error_message = "api_task_cpu/api_task_memory is not a valid AWS Fargate combination."
  }
}

check "fargate_cpu_memory_valid_for_workers" {
  assert {
    condition = contains(
      local.allowed_fargate_memory_by_cpu[tostring(var.worker_task_cpu)],
      var.worker_task_memory,
    )
    error_message = "worker_task_cpu/worker_task_memory is not a valid AWS Fargate combination."
  }
}

check "non_dev_rds_safety_defaults" {
  assert {
    condition = (
      local.is_dev_environment ||
      var.allow_unsafe_rds_configuration ||
      (
        local.rds_deletion_protection_effective &&
        !local.rds_skip_final_snapshot_effective
      )
    )
    error_message = "For staging/prod, keep RDS deletion protection enabled and final snapshot creation enabled. Set allow_unsafe_rds_configuration=true only for approved break-glass operations."
  }
}

check "cur_reconciliation_configuration_complete" {
  assert {
    condition     = (!local.cur_config_any) || local.cur_config_complete
    error_message = "Set all CUR Athena fields together (cur_athena_database, cur_athena_table, cur_athena_output_location), or leave all empty to disable reconciliation."
  }
}

resource "aws_kms_key" "control_plane" {
  description             = "KMS key for SparkPilot ${var.environment} control plane"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  tags                    = local.tags
}

resource "aws_kms_alias" "control_plane" {
  name          = "alias/${local.name_prefix}-control-plane"
  target_key_id = aws_kms_key.control_plane.key_id
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/${local.name_prefix}/api"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.control_plane.arn
  tags              = local.tags
}

resource "aws_cloudwatch_log_group" "workers" {
  name              = "/${local.name_prefix}/workers"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.control_plane.arn
  tags              = local.tags
}

resource "aws_sqs_queue" "provisioning_dlq" {
  name              = "${local.name_prefix}-provisioning-dlq"
  kms_master_key_id = aws_kms_key.control_plane.arn
  tags              = local.tags
}

resource "aws_sqs_queue" "provisioning" {
  name              = "${local.name_prefix}-provisioning"
  kms_master_key_id = aws_kms_key.control_plane.arn
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.provisioning_dlq.arn
    maxReceiveCount     = 5
  })
  tags = local.tags
}

resource "aws_sqs_queue" "runs_dlq" {
  name              = "${local.name_prefix}-runs-dlq"
  kms_master_key_id = aws_kms_key.control_plane.arn
  tags              = local.tags
}

resource "aws_sqs_queue" "runs" {
  name              = "${local.name_prefix}-runs"
  kms_master_key_id = aws_kms_key.control_plane.arn
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.runs_dlq.arn
    maxReceiveCount     = 5
  })
  tags = local.tags
}

resource "aws_ecs_cluster" "control_plane" {
  name = "${local.name_prefix}-ecs"
  tags = local.tags
}

resource "aws_db_subnet_group" "postgres" {
  name       = "${local.name_prefix}-db-subnets"
  subnet_ids = var.private_subnet_ids
  tags       = local.tags
}

resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb"
  description = "SparkPilot API ALB security group"
  vpc_id      = var.vpc_id
  tags        = local.tags
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
  description       = "Allow HTTP ingress to SparkPilot API ALB"
}

resource "aws_vpc_security_group_egress_rule" "alb_all" {
  security_group_id = aws_security_group.alb.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "Allow all ALB egress"
}

resource "aws_security_group" "ecs_tasks" {
  name        = "${local.name_prefix}-ecs-tasks"
  description = "SparkPilot ECS task security group"
  vpc_id      = var.vpc_id
  tags        = local.tags
}

resource "aws_vpc_security_group_ingress_rule" "ecs_api_from_alb" {
  security_group_id            = aws_security_group.ecs_tasks.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
  description                  = "Allow API traffic from ALB to ECS tasks"
}

resource "aws_vpc_security_group_egress_rule" "ecs_tasks_all" {
  security_group_id = aws_security_group.ecs_tasks.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "Allow all ECS task egress"
}

resource "aws_security_group" "postgres" {
  name        = "${local.name_prefix}-postgres"
  description = "SparkPilot postgres security group"
  vpc_id      = var.vpc_id
  tags        = local.tags
}

resource "aws_vpc_security_group_ingress_rule" "postgres_from_ecs" {
  security_group_id            = aws_security_group.postgres.id
  referenced_security_group_id = aws_security_group.ecs_tasks.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "Allow PostgreSQL access from ECS tasks"
}

resource "aws_vpc_security_group_egress_rule" "postgres_all" {
  security_group_id = aws_security_group.postgres.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
  description       = "Allow all postgres egress"
}

resource "aws_db_instance" "postgres" {
  identifier                      = "${local.name_prefix}-postgres"
  engine                          = "postgres"
  engine_version                  = "16.4"
  allocated_storage               = var.db_allocated_storage
  storage_type                    = "gp3"
  db_name                         = var.db_name
  username                        = var.db_username
  password                        = var.db_password
  instance_class                  = var.db_instance_class
  db_subnet_group_name            = aws_db_subnet_group.postgres.name
  vpc_security_group_ids          = [aws_security_group.postgres.id]
  skip_final_snapshot             = local.rds_skip_final_snapshot_effective
  final_snapshot_identifier       = local.rds_final_snapshot_identifier_effective
  backup_retention_period         = 7
  deletion_protection             = local.rds_deletion_protection_effective
  storage_encrypted               = true
  kms_key_id                      = aws_kms_key.control_plane.arn
  performance_insights_enabled    = true
  performance_insights_kms_key_id = aws_kms_key.control_plane.arn
  copy_tags_to_snapshot           = true
  tags                            = local.tags
}

resource "aws_lb" "api" {
  name                       = local.alb_name
  internal                   = local.alb_internal
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb.id]
  subnets                    = local.alb_subnet_ids
  enable_deletion_protection = var.alb_deletion_protection
  idle_timeout               = 120
  tags                       = local.tags
}

resource "aws_lb_target_group" "api" {
  name        = local.api_tg_name
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"
  health_check {
    enabled             = true
    path                = "/healthz"
    port                = "traffic-port"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }
  tags = local.tags
}

resource "aws_lb_listener" "api_http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

data "aws_iam_policy_document" "ecs_task_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  name               = "${local.name_prefix}-ecs-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "ecs_task_runtime" {
  statement {
    sid = "AllowSqsControlPlaneQueues"
    actions = [
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ReceiveMessage",
      "sqs:SendMessage",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [
      aws_sqs_queue.provisioning.arn,
      aws_sqs_queue.provisioning_dlq.arn,
      aws_sqs_queue.runs.arn,
      aws_sqs_queue.runs_dlq.arn,
    ]
  }

  statement {
    sid = "AllowAssumeCustomerRoles"
    actions = [
      "sts:AssumeRole",
      "sts:GetCallerIdentity",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "ecs_task_runtime" {
  name               = "${local.name_prefix}-ecs-task-runtime"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json
  tags               = local.tags
}

resource "aws_iam_role_policy" "ecs_task_runtime_inline" {
  name   = "${local.name_prefix}-ecs-task-runtime"
  role   = aws_iam_role.ecs_task_runtime.id
  policy = data.aws_iam_policy_document.ecs_task_runtime.json
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name_prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.api_task_cpu)
  memory                   = tostring(var.api_task_memory)
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_runtime.arn
  container_definitions = jsonencode([
    {
      name      = "sparkpilot-api"
      image     = var.api_image_uri
      essential = true
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]
      environment = local.common_runtime_env
      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=5)\""]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 20
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "api"
        }
      }
    }
  ])
  tags = local.tags
}

resource "aws_ecs_task_definition" "worker" {
  for_each                 = local.worker_specs
  family                   = "${local.name_prefix}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.worker_task_cpu)
  memory                   = tostring(var.worker_task_memory)
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task_runtime.arn
  container_definitions = jsonencode([
    {
      name        = "sparkpilot-${each.key}"
      image       = var.worker_image_uri
      essential   = true
      command     = each.value
      environment = local.common_runtime_env
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.workers.name
          awslogs-region        = var.region
          awslogs-stream-prefix = each.key
        }
      }
    }
  ])
  tags = local.tags
}

resource "aws_ecs_service" "api" {
  name                               = local.api_task_name
  cluster                            = aws_ecs_cluster.control_plane.id
  task_definition                    = aws_ecs_task_definition.api.arn
  desired_count                      = var.api_desired_count
  launch_type                        = "FARGATE"
  health_check_grace_period_seconds  = 60
  enable_execute_command             = true
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "sparkpilot-api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.api_http]
  tags       = local.tags
}

resource "aws_ecs_service" "worker" {
  for_each                           = local.worker_specs
  name                               = substr(replace("${local.name_prefix}-${each.key}", "_", "-"), 0, 32)
  cluster                            = aws_ecs_cluster.control_plane.id
  task_definition                    = aws_ecs_task_definition.worker[each.key].arn
  desired_count                      = lookup(var.worker_desired_count_by_service, each.key, var.worker_desired_count)
  launch_type                        = "FARGATE"
  enable_execute_command             = true
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  tags = local.tags
}
