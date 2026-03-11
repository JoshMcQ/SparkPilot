output "eks_cluster_arn" {
  value       = module.eks.cluster_arn
  description = "ARN of the EKS cluster."
}

output "eks_cluster_name" {
  value       = module.eks.cluster_name
  description = "Name of the EKS cluster."
}

output "oidc_provider_arn" {
  value       = module.eks.oidc_provider_arn
  description = "ARN of the IAM OIDC provider for the EKS cluster."
}

output "oidc_provider_url" {
  value       = module.eks.cluster_oidc_issuer_url
  description = "URL of the OIDC issuer for the EKS cluster."
}
