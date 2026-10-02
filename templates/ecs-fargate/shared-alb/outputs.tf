output "app_url" {
  description = "Public URL of the app: the shared ALB address. The app answers under path_pattern there."
  value       = var.alb_base_url
}

output "cluster_name" {
  value = aws_ecs_cluster.app.name
}

output "service_name" {
  value = aws_ecs_service.app.name
}

output "health_check_path" {
  description = "Path the pipeline checks after apply through the shared address, same as the target group health check."
  value       = var.health_check_path
}

output "task_definition_arn" {
  description = "Revision this deploy registered. The pipeline checks the service is running it (not rolled back)."
  value       = aws_ecs_task_definition.app.arn
}
