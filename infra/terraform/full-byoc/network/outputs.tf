output "vpc_id" {
  value       = module.vpc.vpc_id
  description = "ID of the provisioned VPC."
}

output "private_subnet_ids" {
  value       = module.vpc.private_subnets
  description = "List of private subnet IDs."
}

output "public_subnet_ids" {
  value       = module.vpc.public_subnets
  description = "List of public subnet IDs."
}
