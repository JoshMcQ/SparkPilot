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

variable "stage" {
  type        = string
  description = "Current provisioning stage (e.g. provisioning_network, provisioning_eks, provisioning_emr)."

  validation {
    condition = contains([
      "provisioning_network",
      "provisioning_eks",
      "provisioning_emr",
      "validating_bootstrap",
      "validating_runtime",
    ], var.stage)
    error_message = "stage must be one of: provisioning_network, provisioning_eks, provisioning_emr, validating_bootstrap, validating_runtime."
  }
}

variable "workspace" {
  type        = string
  description = "Deterministic workspace name used by the orchestrator."
}

variable "state_key" {
  type        = string
  description = "Deterministic remote state object key."
}

variable "customer_role_arn" {
  type        = string
  description = "IAM role ARN in the customer account that SparkPilot assumes for provisioning."
}

variable "vpc_cidr" {
  type        = string
  default     = "10.100.0.0/16"
  description = "CIDR block for the VPC (provisioning_network stage)."
}

variable "eks_namespace" {
  type        = string
  default     = "emr-workloads"
  description = "Kubernetes namespace for EMR on EKS Spark workloads (provisioning_emr stage)."
}
