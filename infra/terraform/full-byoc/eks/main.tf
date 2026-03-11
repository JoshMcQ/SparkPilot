terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  name_prefix  = "sp-${substr(var.tenant_id, 0, 8)}-${substr(var.environment_id, 0, 8)}"
  cluster_name = local.name_prefix
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = local.cluster_name
  cluster_version = "1.29"

  vpc_id                         = var.vpc_id
  subnet_ids                     = var.private_subnet_ids
  cluster_endpoint_public_access = true

  enable_irsa = true

  cluster_addons = {
    coredns    = { most_recent = true }
    kube-proxy = { most_recent = true }
    vpc-cni    = { most_recent = true }
  }

  eks_managed_node_groups = {
    on_demand_x86 = {
      name         = "${local.cluster_name}-od-x86"
      min_size     = 2
      max_size     = 20
      desired_size = 2

      capacity_type  = "ON_DEMAND"
      instance_types = ["m7i.xlarge"]

      labels = {
        "sparkpilot.io/pool" = "on-demand"
        "sparkpilot.io/arch" = "amd64"
      }
    }

    spot_arm64 = {
      name         = "${local.cluster_name}-spot-arm64"
      min_size     = 1
      max_size     = 20
      desired_size = 2

      capacity_type  = "SPOT"
      instance_types = ["m7g.xlarge"]

      labels = {
        "sparkpilot.io/pool" = "spot"
        "sparkpilot.io/arch" = "arm64"
      }

      iam_role_additional_policies = {
        AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
      }
    }
  }
}
