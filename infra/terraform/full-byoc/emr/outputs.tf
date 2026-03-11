output "eks_cluster_arn" {
  value       = var.eks_cluster_arn
  description = "EKS cluster ARN (pass-through from EKS stage, consumed by SparkPilot)."
}

output "emr_virtual_cluster_id" {
  value       = aws_emrcontainers_virtual_cluster.this.id
  description = "EMR on EKS virtual cluster ID consumed by SparkPilot full-BYOC provisioning."
}

output "emr_execution_role_arn" {
  value       = aws_iam_role.emr_execution.arn
  description = "ARN of the EMR execution IAM role used for Spark job runs."
}
