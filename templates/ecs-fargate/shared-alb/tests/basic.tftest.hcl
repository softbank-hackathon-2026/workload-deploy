mock_provider "aws" {
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
  application_id        = "app-0123456789ab"
  deployment_id         = "dep-0123456789ab"
  infra_id              = "sbh-workload-demo-vpc-multiaz01"
  image                 = "921810471078.dkr.ecr.ap-northeast-2.amazonaws.com/sbh-workload-demo-ecr-apps@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  vpc_id                = "vpc-092d8b539c0a83343"
  private_subnet_ids    = ["subnet-08e64f2782ec17cdb", "subnet-084820d9aca23f08a"]
  alb_listener_arn      = "arn:aws:elasticloadbalancing:ap-northeast-2:921810471078:listener/app/sbh-workload-demo-multiaz-alb/9e2fb6b8f737f2ad/78f80f454f011830"
  alb_security_group_id = "sg-01291ad39fdb6c425"
  alb_base_url          = "https://demo.howon.me"
  rule_priority         = 100
}

run "web_defaults" {
  command = apply

  assert {
    condition = (
      !aws_ecs_service.app.network_configuration[0].assign_public_ip &&
      aws_ecs_service.app.network_configuration[0].subnets == toset(var.private_subnet_ids) &&
      aws_lb_listener_rule.app.priority == 100 &&
      one(one(aws_lb_listener_rule.app.condition).path_pattern).values == toset(["/*"]) &&
      one(aws_security_group.task.ingress).security_groups == toset(["sg-01291ad39fdb6c425"]) &&
      one(aws_security_group.task.ingress).from_port == 80
    )
    error_message = "Tasks must sit in the private subnets without public IPs, reachable only from the shared ALB, behind a /* rule."
  }

  assert {
    condition     = output.app_url == "https://demo.howon.me"
    error_message = "app_url must be the shared ALB address."
  }
}

run "api_rule" {
  command = plan

  variables {
    path_pattern      = "/api/*"
    rule_priority     = 10
    container_port    = 8080
    health_check_path = "/api/health"
  }

  assert {
    condition = (
      one(one(aws_lb_listener_rule.app.condition).path_pattern).values == toset(["/api/*"]) &&
      aws_lb_listener_rule.app.priority == 10 &&
      aws_lb_target_group.app.port == 8080 &&
      one(aws_lb_target_group.app.health_check).path == "/api/health"
    )
    error_message = "Backend values must reach the listener rule and target group."
  }
}

run "rejects_bad_path" {
  command = plan

  variables {
    path_pattern = "api/*"
  }

  expect_failures = [var.path_pattern]
}

run "rejects_health_check_outside_path" {
  command = plan

  variables {
    path_pattern  = "/api/*"
    rule_priority = 10
  }

  expect_failures = [var.health_check_path]
}

run "rejects_one_subnet" {
  command = plan

  variables {
    private_subnet_ids = ["subnet-08e64f2782ec17cdb"]
  }

  expect_failures = [var.private_subnet_ids]
}

run "rejects_base_url_with_path" {
  command = plan

  variables {
    alb_base_url = "https://demo.howon.me/"
  }

  expect_failures = [var.alb_base_url]
}
