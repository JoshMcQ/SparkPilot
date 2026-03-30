output "kms_key_arn" {
  value       = aws_kms_key.control_plane.arn
  description = "Control plane KMS key ARN."
}

output "ecs_cluster_arn" {
  value       = aws_ecs_cluster.control_plane.arn
  description = "ECS cluster ARN."
}

output "ecs_cluster_name" {
  value       = aws_ecs_cluster.control_plane.name
  description = "ECS cluster name."
}

output "ecs_task_execution_role_arn" {
  value       = aws_iam_role.ecs_task_execution.arn
  description = "IAM role ARN used by ECS task execution."
}

output "ecs_task_runtime_role_arn" {
  value       = aws_iam_role.ecs_task_runtime.arn
  description = "IAM role ARN used by ECS tasks at runtime."
}

output "ecs_api_service_name" {
  value       = aws_ecs_service.api.name
  description = "ECS API service name."
}

output "ecs_worker_service_names" {
  value       = { for key, svc in aws_ecs_service.worker : key => svc.name }
  description = "ECS worker service names by worker type."
}

output "api_load_balancer_dns_name" {
  value       = aws_lb.api.dns_name
  description = "SparkPilot API ALB DNS name."
}

output "api_base_url" {
  value       = local.https_enabled ? "https://${aws_lb.api.dns_name}" : "http://${aws_lb.api.dns_name}"
  description = "SparkPilot API base URL. Uses https:// when acm_certificate_arn is set, http:// otherwise."
}

output "alb_internal" {
  value       = local.alb_internal
  description = "Whether the API ALB is internal-only."
}

output "https_enabled" {
  value       = local.https_enabled
  description = "Whether HTTPS is enabled on the API ALB."
}

output "api_load_balancer_arn" {
  value       = aws_lb.api.arn
  description = "SparkPilot API ALB ARN."
}

output "api_load_balancer_security_group_id" {
  value       = aws_security_group.alb.id
  description = "Security group ID attached to the API ALB."
}

output "api_target_group_arn" {
  value       = aws_lb_target_group.api.arn
  description = "SparkPilot API target group ARN."
}

output "ecs_tasks_security_group_id" {
  value       = aws_security_group.ecs_tasks.id
  description = "Security group ID attached to ECS tasks."
}

output "postgres_security_group_id" {
  value       = aws_security_group.postgres.id
  description = "Security group ID attached to RDS Postgres."
}

output "provisioning_queue_url" {
  value       = aws_sqs_queue.provisioning.url
  description = "Provisioning queue URL."
}

output "provisioning_queue_arn" {
  value       = aws_sqs_queue.provisioning.arn
  description = "Provisioning queue ARN."
}

output "runs_queue_url" {
  value       = aws_sqs_queue.runs.url
  description = "Run orchestration queue URL."
}

output "runs_queue_arn" {
  value       = aws_sqs_queue.runs.arn
  description = "Run orchestration queue ARN."
}

output "postgres_address" {
  value       = aws_db_instance.postgres.address
  description = "RDS endpoint address."
}

output "database_url_secret_arn" {
  value       = aws_secretsmanager_secret.database_url.arn
  description = "Secrets Manager ARN for the SPARKPILOT_DATABASE_URL secret. The deploy script writes the actual value here after apply."
}

output "bootstrap_secret_arn" {
  value       = aws_secretsmanager_secret.bootstrap.arn
  description = "Secrets Manager ARN for the SPARKPILOT_BOOTSTRAP_SECRET secret. The deploy script writes the actual value here after apply."
}

output "postgres_db_name" {
  value       = var.db_name
  description = "RDS database name (used by deploy script to construct the database URL)."
}

output "postgres_db_username" {
  value       = var.db_username
  description = "RDS master username (used by deploy script to construct the database URL)."
}

output "postgres_instance_arn" {
  value       = aws_db_instance.postgres.arn
  description = "RDS instance ARN."
}

output "postgres_identifier" {
  value       = aws_db_instance.postgres.identifier
  description = "RDS instance identifier."
}

output "rds_deletion_protection_effective" {
  value       = aws_db_instance.postgres.deletion_protection
  description = "Effective RDS deletion protection state."
}

output "rds_skip_final_snapshot_effective" {
  value       = aws_db_instance.postgres.skip_final_snapshot
  description = "Effective RDS skip-final-snapshot state."
}

output "api_image_uri_deployed" {
  value       = var.api_image_uri
  description = "Container image URI currently configured for the API task definition."
}

output "worker_image_uri_deployed" {
  value       = var.worker_image_uri
  description = "Container image URI currently configured for worker task definitions."
}
