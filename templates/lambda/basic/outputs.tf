output "app_url" {
  description = "Public URL of the app (function URL, without the trailing slash)."
  value       = trimsuffix(aws_lambda_function_url.app.function_url, "/")
}

output "function_name" {
  value = aws_lambda_function.app.function_name
}

output "health_check_path" {
  description = "Path the pipeline checks after apply."
  value       = var.health_check_path
}
