# One web app as a Lambda container image, public through a function URL. No VPC, no load balancer.
# The pipeline adds the AWS Lambda Web Adapter to the user's image, so a plain HTTP server runs unchanged:
# the adapter starts the app, waits for health_check_path, and turns each Lambda event into an HTTP request.

locals {
  name = "sbh-workload-demo-fn-${var.application_id}"
}

resource "aws_iam_role" "function" {
  name = "sbh-workload-demo-role-fn-${var.application_id}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.function.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Created here so it gets the retention and is removed with the app.
resource "aws_cloudwatch_log_group" "function" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 7
}

resource "aws_lambda_function" "app" {
  function_name = local.name
  role          = aws_iam_role.function.arn
  package_type  = "Image"
  image_uri     = var.image
  # Images are built on GitHub's x86_64 runners.
  architectures = ["x86_64"]
  memory_size   = var.memory
  timeout       = var.timeout

  environment {
    variables = {
      PORT                         = tostring(var.container_port)
      AWS_LWA_PORT                 = tostring(var.container_port)
      AWS_LWA_READINESS_CHECK_PATH = var.health_check_path
    }
  }

  tags = { DeploymentId = var.deployment_id }

  depends_on = [aws_iam_role_policy_attachment.logs, aws_cloudwatch_log_group.function]
}

resource "aws_lambda_function_url" "app" {
  function_name      = aws_lambda_function.app.function_name
  authorization_type = "NONE"
}

# A public function URL needs both permissions: InvokeFunctionUrl and InvokeFunction limited to URL calls.
resource "aws_lambda_permission" "url" {
  statement_id           = "PublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.app.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "invoke" {
  statement_id             = "PublicInvokeViaFunctionUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.app.function_name
  principal                = "*"
  invoked_via_function_url = true
}
