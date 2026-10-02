output "app_url" {
  description = "Public URL of the app (instance public DNS on port 80). Changes when a redeploy replaces the instance."
  value       = "http://${aws_instance.app.public_dns}"
}

output "instance_id" {
  value = aws_instance.app.id
}

output "health_check_path" {
  description = "Path the pipeline checks after apply."
  value       = var.health_check_path
}
