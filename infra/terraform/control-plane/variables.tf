variable "project_name" {
  type        = string
  description = "Project prefix for resource naming."
  default     = "sparkpilot"
  validation {
    condition     = can(regex("^[a-z0-9-]+$", trimspace(var.project_name)))
    error_message = "project_name must use lowercase letters, numbers, and hyphens only."
  }
}

variable "environment" {
  type        = string
  description = "Environment name (dev/staging/prod)."
  validation {
    condition     = contains(["dev", "staging", "prod"], lower(trimspace(var.environment)))
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "region" {
  type        = string
  description = "AWS region."
  default     = "us-east-1"
  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", trimspace(var.region)))
    error_message = "region must be a valid AWS region identifier (example: us-east-1)."
  }
}

variable "vpc_id" {
  type        = string
  description = "VPC ID where control plane resources are deployed."
  validation {
    condition     = can(regex("^vpc-[a-z0-9]+$", trimspace(var.vpc_id)))
    error_message = "vpc_id must look like an AWS VPC ID (vpc-...)."
  }
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for ECS and RDS."
  validation {
    condition = (
      length(var.private_subnet_ids) >= 2 &&
      alltrue([for subnet_id in var.private_subnet_ids : can(regex("^subnet-[a-z0-9]+$", trimspace(subnet_id)))])
    )
    error_message = "private_subnet_ids must include at least two valid subnet IDs."
  }
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "Public subnet IDs for internet-facing ALB. If empty, ALB is internal and private subnets are used."
  default     = []
  validation {
    condition = (
      length(var.public_subnet_ids) == 0 ||
      (
        length(var.public_subnet_ids) >= 2 &&
        alltrue([for subnet_id in var.public_subnet_ids : can(regex("^subnet-[a-z0-9]+$", trimspace(subnet_id)))])
      )
    )
    error_message = "public_subnet_ids must be empty or include at least two valid subnet IDs."
  }
}

variable "default_tags" {
  type        = map(string)
  description = "Common tags applied to all resources."
  default     = {}
}

variable "db_name" {
  type        = string
  description = "RDS Postgres database name."
  default     = "sparkpilot"
}

variable "db_username" {
  type        = string
  description = "RDS Postgres master username."
  default     = "sparkpilot"
}

variable "db_password" {
  type        = string
  description = "RDS Postgres master password."
  sensitive   = true
  validation {
    condition     = length(trimspace(var.db_password)) >= 16
    error_message = "db_password must be at least 16 characters."
  }
}

variable "db_instance_class" {
  type        = string
  description = "RDS instance class."
  default     = "db.t4g.medium"
}

variable "db_allocated_storage" {
  type        = number
  description = "RDS allocated storage in GB."
  default     = 50
  validation {
    condition     = var.db_allocated_storage >= 20
    error_message = "db_allocated_storage must be at least 20 GB."
  }
}

variable "rds_deletion_protection" {
  type        = bool
  nullable    = true
  description = "Override for RDS deletion protection. Null uses environment default (false for dev, true for staging/prod)."
  default     = null
}

variable "rds_skip_final_snapshot" {
  type        = bool
  nullable    = true
  description = "Override for final snapshot on delete. Null uses environment default (true for dev, false for staging/prod)."
  default     = null
}

variable "allow_unsafe_rds_configuration" {
  type        = bool
  description = "Break-glass override that permits unsafe non-dev RDS settings."
  default     = false
}

variable "rds_final_snapshot_identifier" {
  type        = string
  description = "Explicit final snapshot identifier on delete. Leave empty to use <project>-<env>-final."
  default     = ""
  validation {
    condition = (
      trimspace(var.rds_final_snapshot_identifier) == "" ||
      can(regex("^[a-z][a-z0-9-]*$", trimspace(var.rds_final_snapshot_identifier)))
    )
    error_message = "rds_final_snapshot_identifier must be empty or a lowercase snapshot identifier."
  }
}

variable "alb_deletion_protection" {
  type        = bool
  description = "Enable ALB deletion protection."
  default     = true
}

variable "api_image_uri" {
  type        = string
  description = "Container image URI for SparkPilot API."
  validation {
    condition     = length(trimspace(var.api_image_uri)) > 0
    error_message = "api_image_uri must be non-empty."
  }
}

variable "worker_image_uri" {
  type        = string
  description = "Container image URI for SparkPilot workers."
  validation {
    condition     = length(trimspace(var.worker_image_uri)) > 0
    error_message = "worker_image_uri must be non-empty."
  }
}

variable "api_task_cpu" {
  type        = number
  description = "Fargate CPU units for API task."
  default     = 512
  validation {
    condition     = contains([256, 512, 1024, 2048, 4096], var.api_task_cpu)
    error_message = "api_task_cpu must be a supported Fargate CPU value."
  }
}

variable "api_task_memory" {
  type        = number
  description = "Fargate memory (MiB) for API task."
  default     = 1024
  validation {
    condition     = var.api_task_memory >= 512
    error_message = "api_task_memory must be at least 512 MiB."
  }
}

variable "worker_task_cpu" {
  type        = number
  description = "Fargate CPU units for worker task."
  default     = 512
  validation {
    condition     = contains([256, 512, 1024, 2048, 4096], var.worker_task_cpu)
    error_message = "worker_task_cpu must be a supported Fargate CPU value."
  }
}

variable "worker_task_memory" {
  type        = number
  description = "Fargate memory (MiB) for worker task."
  default     = 1024
  validation {
    condition     = var.worker_task_memory >= 512
    error_message = "worker_task_memory must be at least 512 MiB."
  }
}

variable "api_desired_count" {
  type        = number
  description = "Desired number of API tasks."
  default     = 1
  validation {
    condition     = var.api_desired_count >= 1
    error_message = "api_desired_count must be at least 1."
  }
}

variable "worker_desired_count" {
  type        = number
  description = "Default desired number of worker tasks per service."
  default     = 1
  validation {
    condition     = var.worker_desired_count >= 0
    error_message = "worker_desired_count must be zero or greater."
  }
}

variable "worker_desired_count_by_service" {
  type        = map(number)
  description = "Per-service worker desired counts keyed by service name (provisioner/scheduler/reconciler)."
  default     = {}
  validation {
    condition = alltrue([
      for service_name, desired_count in var.worker_desired_count_by_service :
      contains(["provisioner", "scheduler", "reconciler", "cur_reconciliation"], service_name) && desired_count >= 0
    ])
    error_message = "worker_desired_count_by_service keys must be provisioner/scheduler/reconciler/cur_reconciliation and values must be >= 0."
  }
}

variable "dry_run_mode" {
  type        = bool
  description = "SparkPilot runtime dry-run mode."
  default     = false
}

variable "enable_full_byoc_mode" {
  type        = bool
  description = "Enable full-BYOC environment creation."
  default     = false
}

variable "oidc_issuer" {
  type        = string
  description = "OIDC issuer URL used by SparkPilot."
  validation {
    condition     = can(regex("^https?://", trimspace(var.oidc_issuer)))
    error_message = "oidc_issuer must be an http(s) URL."
  }
}

variable "oidc_audience" {
  type        = string
  description = "OIDC audience expected by SparkPilot."
  validation {
    condition     = length(trimspace(var.oidc_audience)) > 0
    error_message = "oidc_audience must be non-empty."
  }
}

variable "oidc_jwks_uri" {
  type        = string
  description = "OIDC JWKS URI used to validate access tokens."
  validation {
    condition     = can(regex("^(https?://|file://)", trimspace(var.oidc_jwks_uri)))
    error_message = "oidc_jwks_uri must start with http://, https://, or file://."
  }
}

# bootstrap_secret is no longer a Terraform variable.
# The deploy script (scripts/terraform/deploy_control_plane.sh) writes the value
# directly to the aws_secretsmanager_secret.bootstrap container via AWS CLI after
# Terraform apply. This keeps the secret out of Terraform state entirely.

variable "emr_execution_role_arn" {
  type        = string
  description = "EMR execution role ARN used for live mode."
  default     = "arn:aws:iam::111111111111:role/SparkPilotEmrExecutionRole"
  validation {
    condition = (
      trimspace(var.emr_execution_role_arn) == "arn:aws:iam::111111111111:role/SparkPilotEmrExecutionRole" ||
      can(regex("^arn:aws:iam::[0-9]{12}:role/.+$", trimspace(var.emr_execution_role_arn)))
    )
    error_message = "emr_execution_role_arn must be a valid IAM role ARN."
  }
}

variable "assume_role_external_id" {
  type        = string
  description = "Optional ExternalId included in SparkPilot runtime AssumeRole calls."
  default     = ""
}

variable "poll_interval_seconds" {
  type        = number
  description = "Worker polling interval seconds."
  default     = 15
  validation {
    condition     = var.poll_interval_seconds >= 1
    error_message = "poll_interval_seconds must be at least 1 second."
  }
}

variable "cors_origins" {
  type        = list(string)
  description = "Credentialed CORS origins for SparkPilot API."
  default     = ["http://localhost:3000", "http://127.0.0.1:3000"]
  validation {
    condition = (
      length(var.cors_origins) > 0 &&
      alltrue([
        for origin in var.cors_origins :
        can(regex("^https?://[^*\\s]+$", trimspace(origin)))
      ])
    )
    error_message = "cors_origins must include valid http(s) origins and cannot include wildcards."
  }
}

variable "cur_athena_database" {
  type        = string
  description = "Athena database containing CUR data. Leave empty to disable CUR reconciliation."
  default     = ""
  validation {
    condition = (
      trimspace(var.cur_athena_database) == "" ||
      can(regex("^[A-Za-z_][A-Za-z0-9_]*$", trimspace(var.cur_athena_database)))
    )
    error_message = "cur_athena_database must be empty or a valid Athena identifier."
  }
}

variable "cur_athena_table" {
  type        = string
  description = "Athena table containing CUR data. Leave empty to disable CUR reconciliation."
  default     = ""
  validation {
    condition = (
      trimspace(var.cur_athena_table) == "" ||
      can(regex("^[A-Za-z_][A-Za-z0-9_]*$", trimspace(var.cur_athena_table)))
    )
    error_message = "cur_athena_table must be empty or a valid Athena identifier."
  }
}

variable "cur_athena_workgroup" {
  type        = string
  description = "Athena workgroup used for CUR reconciliation queries."
  default     = "primary"
  validation {
    condition = (
      trimspace(var.cur_athena_workgroup) != "" &&
      can(regex("^[A-Za-z0-9._-]+$", trimspace(var.cur_athena_workgroup)))
    )
    error_message = "cur_athena_workgroup must be non-empty and contain only letters, numbers, dot, underscore, or hyphen."
  }
}

variable "cur_athena_output_location" {
  type        = string
  description = "Athena query output S3 location (s3://...). Leave empty to disable CUR reconciliation."
  default     = ""
  validation {
    condition = (
      trimspace(var.cur_athena_output_location) == "" ||
      can(regex("^s3://.+", trimspace(var.cur_athena_output_location)))
    )
    error_message = "cur_athena_output_location must be empty or a valid s3:// URI."
  }
}

variable "cur_run_id_column" {
  type        = string
  description = "CUR column containing SparkPilot run id tag."
  default     = "resource_tags_user_sparkpilot_run_id"
  validation {
    condition     = can(regex("^[A-Za-z_][A-Za-z0-9_]*$", trimspace(var.cur_run_id_column)))
    error_message = "cur_run_id_column must be a valid Athena identifier."
  }
}

variable "cur_cost_column" {
  type        = string
  description = "CUR numeric cost column used for reconciliation."
  default     = "line_item_unblended_cost"
  validation {
    condition     = can(regex("^[A-Za-z_][A-Za-z0-9_]*$", trimspace(var.cur_cost_column)))
    error_message = "cur_cost_column must be a valid Athena identifier."
  }
}

variable "cost_center_policy_json" {
  type        = string
  description = "Optional JSON policy for namespace/virtual-cluster/team cost center mapping."
  default     = ""
  validation {
    condition = (
      trimspace(var.cost_center_policy_json) == "" ||
      can(jsondecode(var.cost_center_policy_json))
    )
    error_message = "cost_center_policy_json must be empty or valid JSON."
  }
}

variable "acm_certificate_arn" {
  type        = string
  description = "ACM certificate ARN for HTTPS on the API ALB. When set, HTTP redirects to HTTPS and the API is served on port 443. Leave empty for HTTP-only (dev/internal use)."
  default     = ""
  validation {
    condition = (
      trimspace(var.acm_certificate_arn) == "" ||
      can(regex("^arn:aws:acm:[a-z0-9-]+:[0-9]{12}:certificate/[a-f0-9-]+$", trimspace(var.acm_certificate_arn)))
    )
    error_message = "acm_certificate_arn must be empty or a valid ACM certificate ARN."
  }
}

variable "enable_ecs_exec" {
  type        = bool
  description = "Enable ECS Exec (SSM shell access to containers). Disable in production to reduce attack surface."
  default     = false
}
