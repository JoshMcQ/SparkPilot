variable "tenant_id" {
  type        = string
  description = "SparkPilot tenant identifier."
}

variable "environment_id" {
  type        = string
  description = "SparkPilot environment identifier."
}

variable "region" {
  type        = string
  description = "AWS region for the customer runtime."
}

variable "customer_role_arn" {
  type        = string
  description = "IAM role ARN in the customer account that SparkPilot assumes for provisioning."
}

variable "vpc_cidr" {
  type        = string
  default     = "10.100.0.0/16"
  description = "CIDR block for the VPC."
}
