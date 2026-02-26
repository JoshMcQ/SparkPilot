variable "project_name" {
  type        = string
  description = "Project prefix for resource naming."
  default     = "sparkpilot"
}

variable "environment" {
  type        = string
  description = "Environment name (dev/staging/prod)."
}

variable "region" {
  type        = string
  description = "AWS region."
  default     = "us-east-1"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID where control plane resources are deployed."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for ECS and RDS."
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
}

variable "db_instance_class" {
  type        = string
  description = "RDS instance class."
  default     = "db.t4g.medium"
}

