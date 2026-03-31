terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region

  dynamic "assume_role" {
    for_each = var.customer_role_arn != "" ? [var.customer_role_arn] : []
    content {
      role_arn     = assume_role.value
      external_id  = var.assume_role_external_id != "" ? var.assume_role_external_id : null
    }
  }

  default_tags {
    tags = {
      "sparkpilot:tenant_id"      = var.tenant_id
      "sparkpilot:environment_id" = var.environment_id
      "sparkpilot:managed_by"     = "sparkpilot-full-byoc"
    }
  }
}

locals {
  network_enabled = contains(
    ["provisioning_network", "provisioning_eks", "provisioning_emr"],
    var.stage,
  )
  eks_enabled = contains(["provisioning_eks", "provisioning_emr"], var.stage)
  emr_enabled = var.stage == "provisioning_emr"
}

module "network" {
  source = "./network"
  count  = local.network_enabled ? 1 : 0

  tenant_id      = var.tenant_id
  environment_id = var.environment_id
  region         = var.region
  vpc_cidr       = var.vpc_cidr

  customer_role_arn = var.customer_role_arn
}

module "eks" {
  source = "./eks"
  count  = local.eks_enabled ? 1 : 0

  tenant_id      = var.tenant_id
  environment_id = var.environment_id
  region         = var.region

  customer_role_arn  = var.customer_role_arn
  vpc_id             = module.network[0].vpc_id
  private_subnet_ids = module.network[0].private_subnet_ids
}

module "emr" {
  source = "./emr"
  count  = local.emr_enabled ? 1 : 0

  tenant_id      = var.tenant_id
  environment_id = var.environment_id
  region         = var.region

  customer_role_arn = var.customer_role_arn
  eks_cluster_arn   = module.eks[0].eks_cluster_arn
  eks_cluster_name  = module.eks[0].eks_cluster_name
  oidc_provider_arn = module.eks[0].oidc_provider_arn
  eks_namespace     = var.eks_namespace
}

output "vpc_id" {
  value       = local.network_enabled ? module.network[0].vpc_id : null
  description = "VPC ID (populated during provisioning_network stage)."
}

output "private_subnet_ids" {
  value       = local.network_enabled ? module.network[0].private_subnet_ids : null
  description = "Private subnet IDs (populated during provisioning_network stage)."
}

output "public_subnet_ids" {
  value       = local.network_enabled ? module.network[0].public_subnet_ids : null
  description = "Public subnet IDs (populated during provisioning_network stage)."
}

output "eks_cluster_arn" {
  value       = local.eks_enabled ? module.eks[0].eks_cluster_arn : null
  description = "EKS cluster ARN (populated during provisioning_eks and provisioning_emr stages)."
}

output "eks_cluster_name" {
  value       = local.eks_enabled ? module.eks[0].eks_cluster_name : null
  description = "EKS cluster name (populated during provisioning_eks and provisioning_emr stages)."
}

output "oidc_provider_arn" {
  value       = local.eks_enabled ? module.eks[0].oidc_provider_arn : null
  description = "OIDC provider ARN (populated during provisioning_eks and provisioning_emr stages)."
}

output "emr_virtual_cluster_id" {
  value       = local.emr_enabled ? module.emr[0].emr_virtual_cluster_id : null
  description = "EMR virtual cluster ID (populated during provisioning_emr stage)."
}

output "emr_execution_role_arn" {
  value       = local.emr_enabled ? module.emr[0].emr_execution_role_arn : null
  description = "EMR execution role ARN (populated during provisioning_emr stage)."
}
