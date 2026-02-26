terraform {
  required_version = ">= 1.7.0"

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
}

resource "aws_kms_key" "control_plane" {
  description             = "KMS key for SparkPilot ${var.environment} control plane"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_kms_alias" "control_plane" {
  name          = "alias/${local.name_prefix}-control-plane"
  target_key_id = aws_kms_key.control_plane.key_id
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/${local.name_prefix}/api"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.control_plane.arn
}

resource "aws_cloudwatch_log_group" "workers" {
  name              = "/${local.name_prefix}/workers"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.control_plane.arn
}

resource "aws_sqs_queue" "provisioning_dlq" {
  name              = "${local.name_prefix}-provisioning-dlq"
  kms_master_key_id = aws_kms_key.control_plane.arn
}

resource "aws_sqs_queue" "provisioning" {
  name              = "${local.name_prefix}-provisioning"
  kms_master_key_id = aws_kms_key.control_plane.arn
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.provisioning_dlq.arn
    maxReceiveCount     = 5
  })
}

resource "aws_sqs_queue" "runs_dlq" {
  name              = "${local.name_prefix}-runs-dlq"
  kms_master_key_id = aws_kms_key.control_plane.arn
}

resource "aws_sqs_queue" "runs" {
  name              = "${local.name_prefix}-runs"
  kms_master_key_id = aws_kms_key.control_plane.arn
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.runs_dlq.arn
    maxReceiveCount     = 5
  })
}

resource "aws_ecs_cluster" "control_plane" {
  name = "${local.name_prefix}-ecs"
}

resource "aws_db_subnet_group" "postgres" {
  name       = "${local.name_prefix}-db-subnets"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "postgres" {
  name        = "${local.name_prefix}-postgres"
  description = "SparkPilot postgres security group"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "postgres" {
  identifier                = "${local.name_prefix}-postgres"
  engine                    = "postgres"
  engine_version            = "16.4"
  allocated_storage         = 50
  storage_type              = "gp3"
  db_name                   = "sparkpilot"
  username                  = var.db_username
  password                  = var.db_password
  instance_class            = var.db_instance_class
  db_subnet_group_name      = aws_db_subnet_group.postgres.name
  vpc_security_group_ids    = [aws_security_group.postgres.id]
  skip_final_snapshot       = true
  backup_retention_period   = 7
  deletion_protection       = false
  storage_encrypted         = true
  kms_key_id                = aws_kms_key.control_plane.arn
  performance_insights_enabled = true
}

