output "app_url" {
  description = "Public URL of the app (ALB address)."
  value       = "http://${aws_lb.app.dns_name}"
}

output "cluster_name" {
  value = aws_ecs_cluster.app.name
}

output "service_name" {
  value = aws_ecs_service.app.name
}

output "health_check_path" {
  description = "Path the pipeline checks after apply, same as the target group health check."
  value       = var.health_check_path
}

output "task_definition_arn" {
  description = "Revision this deploy registered. The pipeline checks the service is running it (not rolled back)."
  value       = aws_ecs_task_definition.app.arn
}
