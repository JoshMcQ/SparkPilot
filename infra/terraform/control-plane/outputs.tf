output "kms_key_arn" {
  value       = aws_kms_key.control_plane.arn
  description = "Control plane KMS key ARN."
}

output "ecs_cluster_name" {
  value       = aws_ecs_cluster.control_plane.name
  description = "ECS cluster name."
}

output "provisioning_queue_url" {
  value       = aws_sqs_queue.provisioning.url
  description = "Provisioning queue URL."
}

output "runs_queue_url" {
  value       = aws_sqs_queue.runs.url
  description = "Run orchestration queue URL."
}

output "postgres_address" {
  value       = aws_db_instance.postgres.address
  description = "RDS endpoint address."
}

