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

variable "eks_cluster_arn" {
  type        = string
  description = "ARN of the provisioned EKS cluster (from EKS stage output)."
}

variable "eks_cluster_name" {
  type        = string
  description = "Name of the provisioned EKS cluster (from EKS stage output)."
}

variable "oidc_provider_arn" {
  type        = string
  description = "ARN of the OIDC IAM provider for the EKS cluster (from EKS stage output)."
}

variable "eks_namespace" {
  type        = string
  default     = "emr-workloads"
  description = "Kubernetes namespace where EMR on EKS will run Spark jobs."
}
