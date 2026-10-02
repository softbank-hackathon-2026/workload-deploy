mock_provider "aws" {
  mock_data "aws_ssm_parameter" {
    defaults = { insecure_value = "ami-0123456789abcdef0" }
  }
  mock_resource "aws_instance" {
    defaults = { public_dns = "ec2-3-34-0-1.ap-northeast-2.compute.amazonaws.com" }
  }
}

variables {
  application_id    = "app-0123456789ab"
  deployment_id     = "dep-0123456789ab"
  infra_id          = "sbh-workload-demo-vpc-public01"
  image             = "921810471078.dkr.ecr.ap-northeast-2.amazonaws.com/sbh-workload-demo-ecr-apps@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  vpc_id            = "vpc-0c7ca2fe59980fcea"
  public_subnet_ids = ["subnet-06316627ef6ec5610", "subnet-0c417695633bf550f"]
}

run "defaults" {
  command = apply

  assert {
    condition = (
      aws_instance.app.instance_type == "t3.micro" &&
      aws_instance.app.subnet_id == "subnet-06316627ef6ec5610" &&
      aws_instance.app.associate_public_ip_address &&
      aws_instance.app.metadata_options[0].http_tokens == "required" &&
      strcontains(aws_instance.app.user_data, "-p 80:80 -e PORT=80") &&
      strcontains(aws_instance.app.user_data, "--password-stdin 921810471078.dkr.ecr.ap-northeast-2.amazonaws.com")
    )
    error_message = "Defaults must give a public t3.micro with IMDSv2 that logs in to the image registry and serves port 80."
  }

  assert {
    condition     = output.app_url == "http://ec2-3-34-0-1.ap-northeast-2.compute.amazonaws.com"
    error_message = "app_url must be the instance public DNS."
  }
}

run "filled_values" {
  command = plan

  variables {
    container_port    = 3000
    instance_type     = "t3.small"
    health_check_path = "/health"
  }

  assert {
    condition = (
      aws_instance.app.instance_type == "t3.small" &&
      strcontains(aws_instance.app.user_data, "-p 80:3000 -e PORT=3000") &&
      output.health_check_path == "/health"
    )
    error_message = "AI values must reach the instance."
  }
}

run "rejects_large_instance" {
  command = plan

  variables {
    instance_type = "p3.2xlarge"
  }

  expect_failures = [var.instance_type]
}

run "rejects_non_ecr_image" {
  command = plan

  variables {
    image = "docker.io/library/nginx@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }

  expect_failures = [var.image]
}
