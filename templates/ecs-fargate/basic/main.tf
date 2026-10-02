# One app on Fargate behind its own internet-facing ALB, inside a public Infra Space (VPC + public subnets only).
# ponytail: one ALB per app keeps every app at the root path with no DNS work, but ALB creation adds a few minutes.
# Move the ALB and cluster into a shared Space stack with host-based rules if deploys are too slow for the demo.

locals {
  prefix = "sbh-workload-demo"
  # ALB and target group names are limited to 32 characters (ADR-005).
  short = "sbh-${var.application_id}"
}

resource "aws_ecs_cluster" "app" {
  name = "${local.prefix}-ecs-${var.application_id}"
  tags = { Name = "${local.prefix}-ecs-${var.application_id}" }
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.prefix}-${var.application_id}"
  retention_in_days = 7
}

resource "aws_iam_role" "execution" {
  name = "${local.prefix}-role-exec-${var.application_id}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_security_group" "alb" {
  name        = "${local.prefix}-sg-alb-${var.application_id}"
  description = "HTTP from the internet to the app ALB"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.prefix}-sg-alb-${var.application_id}" }
}

resource "aws_security_group" "task" {
  name        = "${local.prefix}-sg-task-${var.application_id}"
  description = "App port from the ALB only"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  # Pulling the image from ECR and sending logs go out through the public IP.
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.prefix}-sg-task-${var.application_id}" }
}

resource "aws_lb" "app" {
  name               = "${local.short}-alb"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids
  tags               = { Name = "${local.short}-alb" }
}

resource "aws_lb_target_group" "app" {
  name                 = "${local.short}-tg"
  port                 = var.container_port
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = var.vpc_id
  # Time for an old task to finish in-flight requests during a redeploy. Short, because deploy time matters for the demo.
  deregistration_delay = 5

  # Short interval so a new task turns healthy (and the deploy finishes) sooner.
  health_check {
    path                = var.health_check_path
    matcher             = "200-399"
    interval            = 5
    timeout             = 4
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = { Name = "${local.short}-tg" }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_ecs_task_definition" "app" {
  family                   = "${local.prefix}-task-${var.application_id}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn

  # Images are built on GitHub's x86_64 runners.
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name         = "app"
    image        = var.image
    essential    = true
    portMappings = [{ containerPort = var.container_port, protocol = "tcp" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "app"
      }
    }
  }])

  tags = { DeploymentId = var.deployment_id }
}

resource "aws_ecs_service" "app" {
  name            = "${local.prefix}-svc-${var.application_id}"
  cluster         = aws_ecs_cluster.app.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = var.container_port
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # apply returns only after the new task is running and healthy, so the pipeline can verify right after.
  wait_for_steady_state = true

  tags = { DeploymentId = var.deployment_id }

  # Fail well inside the pipeline's 20-minute deploy job instead of waiting on a task that never gets healthy.
  timeouts {
    create = "10m"
    update = "10m"
  }

  depends_on = [aws_lb_listener.http, aws_iam_role_policy_attachment.execution]
}
