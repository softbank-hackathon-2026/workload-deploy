mock_provider "aws" {
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/sbh-workload-demo-role-fn-app-test" }
  }
  mock_resource "aws_lambda_function_url" {
    defaults = { function_url = "https://abc123.lambda-url.ap-northeast-2.on.aws/" }
  }
}

variables {
  application_id = "app-0123456789ab"
  deployment_id  = "dep-0123456789ab"
  infra_id       = "sbh-workload-demo-vpc-public01"
  image          = "921810471078.dkr.ecr.ap-northeast-2.amazonaws.com/sbh-workload-demo-ecr-apps@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}

run "defaults" {
  command = apply

  assert {
    condition = (
      aws_lambda_function.app.package_type == "Image" &&
      aws_lambda_function.app.memory_size == 512 && aws_lambda_function.app.timeout == 30 &&
      aws_lambda_function.app.environment[0].variables["AWS_LWA_PORT"] == "8080" &&
      aws_lambda_function.app.environment[0].variables["PORT"] == "8080" &&
      aws_lambda_function_url.app.authorization_type == "NONE"
    )
    error_message = "Defaults must give a public image function with the adapter on port 8080."
  }

  assert {
    condition     = output.app_url == "https://abc123.lambda-url.ap-northeast-2.on.aws"
    error_message = "app_url must be the function URL without the trailing slash."
  }
}

run "filled_values" {
  command = plan

  variables {
    container_port    = 3000
    memory            = 1024
    timeout           = 60
    health_check_path = "/health"
  }

  assert {
    condition = (
      aws_lambda_function.app.environment[0].variables["AWS_LWA_PORT"] == "3000" &&
      aws_lambda_function.app.environment[0].variables["AWS_LWA_READINESS_CHECK_PATH"] == "/health" &&
      aws_lambda_function.app.memory_size == 1024 && aws_lambda_function.app.timeout == 60
    )
    error_message = "AI values must reach the function."
  }
}

run "rejects_bad_memory" {
  command = plan

  variables {
    memory = 64
  }

  expect_failures = [var.memory]
}

run "rejects_bad_timeout" {
  command = plan

  variables {
    timeout = 901
  }

  expect_failures = [var.timeout]
}

run "rejects_unpinned_image" {
  command = plan

  variables {
    image = "sbh-workload-demo-ecr-apps:latest"
  }

  expect_failures = [var.image]
}
