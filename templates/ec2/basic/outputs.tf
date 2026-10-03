output "app_url" {
  description = "Public URL of the app (instance public DNS on port 80). Changes when a redeploy replaces the instance."
  value       = "http://${aws_instance.app.public_dns}"
}

output "instance_id" {
  value = aws_instance.app.id
}

output "log_group_name" {
  description = "CloudWatch log group with the app's stdout/stderr. Streams are <deployment_id>/<instance_id>/app."
  value       = aws_cloudwatch_log_group.app.name
}

output "log_group_arn" {
  value = aws_cloudwatch_log_group.app.arn
}

output "health_check_path" {
  description = "Path the pipeline checks after apply."
  value       = var.health_check_path
}
