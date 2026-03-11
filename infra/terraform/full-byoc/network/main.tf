terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name_prefix = "sp-${substr(var.tenant_id, 0, 8)}-${substr(var.environment_id, 0, 8)}"

  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  vpc_cidr = var.vpc_cidr

  # Split the /16 into /18 subnets: first two private, next two public
  private_subnets = [
    cidrsubnet(local.vpc_cidr, 2, 0),
    cidrsubnet(local.vpc_cidr, 2, 1),
  ]
  public_subnets = [
    cidrsubnet(local.vpc_cidr, 2, 2),
    cidrsubnet(local.vpc_cidr, 2, 3),
  ]
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = local.name_prefix
  cidr = local.vpc_cidr
  azs  = local.azs

  private_subnets = local.private_subnets
  public_subnets  = local.public_subnets

  enable_nat_gateway     = true
  single_nat_gateway     = false
  one_nat_gateway_per_az = true
  enable_dns_hostnames   = true
  enable_dns_support     = true

  # Required EKS subnet tags
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"            = "1"
    "kubernetes.io/cluster/${local.name_prefix}" = "shared"
  }
  public_subnet_tags = {
    "kubernetes.io/role/elb"                     = "1"
    "kubernetes.io/cluster/${local.name_prefix}" = "shared"
  }
}
