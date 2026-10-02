mock_provider "aws" {
  mock_resource "aws_lb" {
    defaults = {
      arn      = "arn:aws:elasticloadbalancing:ap-northeast-2:123456789012:loadbalancer/app/sbh-app-test/0123456789abcdef"
      dns_name = "sbh-app-test-alb-123.ap-northeast-2.elb.amazonaws.com"
    }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:ap-northeast-2:123456789012:targetgroup/sbh-app-test-tg/0123456789abcdef" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/sbh-workload-demo-role-exec-app-test" }
  }
  mock_resource "aws_ecs_task_definition" {
    defaults = { arn = "arn:aws:ecs:ap-northeast-2:123456789012:task-definition/sbh-workload-demo-task-app-test:1" }
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
      length(aws_lb.app.name) <= 32 && length(aws_lb_target_group.app.name) <= 32 &&
      aws_ecs_service.app.network_configuration[0].assign_public_ip &&
      aws_ecs_service.app.launch_type == "FARGATE" && aws_ecs_service.app.desired_count == 1 &&
      aws_ecs_service.app.wait_for_steady_state &&
      aws_lb_target_group.app.port == 80 && aws_lb_target_group.app.target_type == "ip" &&
      aws_ecs_task_definition.app.cpu == "256" && aws_ecs_task_definition.app.memory == "512"
    )
    error_message = "Defaults must give a public-IP Fargate task behind an ip target group with names within 32 characters."
  }

  assert {
    condition     = output.app_url == "http://sbh-app-test-alb-123.ap-northeast-2.elb.amazonaws.com"
    error_message = "app_url must be the ALB address."
  }
}

run "filled_values" {
  command = plan

  variables {
    container_port    = 3000
    cpu               = 512
    memory            = 1024
    health_check_path = "/healthz"
  }

  assert {
    condition = (
      aws_lb_target_group.app.port == 3000 && aws_lb_target_group.app.health_check[0].path == "/healthz" &&
      one([for r in aws_security_group.task.ingress : r.from_port]) == 3000 &&
      jsondecode(aws_ecs_task_definition.app.container_definitions)[0].portMappings[0].containerPort == 3000 &&
      jsondecode(aws_ecs_task_definition.app.container_definitions)[0].environment[0].name == "PORT" &&
      jsondecode(aws_ecs_task_definition.app.container_definitions)[0].environment[0].value == "3000"
    )
    error_message = "container_port must reach the target group, security group, task port mapping and the PORT variable."
  }
}

run "rejects_long_application_id" {
  command = plan
  variables {
    application_id = "app-0123456789abcdef012345"
  }
  expect_failures = [var.application_id]
}

run "rejects_invalid_memory" {
  command = plan
  variables {
    cpu    = 256
    memory = 4096
  }
  expect_failures = [var.memory]
}

run "rejects_image_without_digest" {
  command = plan
  variables {
    image = "nginx:latest"
  }
  expect_failures = [var.image]
}

run "rejects_bad_health_check_path" {
  command = plan
  variables {
    health_check_path = "health; rm -rf /"
  }
  expect_failures = [var.health_check_path]
}
