# One app on a single EC2 instance in a public Infra Space. The instance runs the same image as ecs-fargate/basic with Docker
# and serves it on port 80 through its public IP. No load balancer.
# ponytail: a redeploy replaces the instance (new image = new user_data), so the address changes and there is a short gap.
# Add an Elastic IP or an ALB if the app needs a fixed address or zero-downtime deploys.

locals {
  name     = "sbh-workload-demo-ec2-${var.application_id}"
  registry = split("/", var.image)[0]
}

# Latest Amazon Linux 2023, which ships the AWS CLI and has Docker in its package repository.
data "aws_ssm_parameter" "ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_iam_role" "instance" {
  name = "sbh-workload-demo-role-ec2-${var.application_id}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Pull the app image from the Workload ECR.
resource "aws_iam_role_policy_attachment" "ecr" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Session Manager instead of SSH keys, for looking at a failed instance.
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "instance" {
  name = "sbh-workload-demo-profile-ec2-${var.application_id}"
  role = aws_iam_role.instance.name
}

resource "aws_security_group" "instance" {
  name        = "sbh-workload-demo-sg-ec2-${var.application_id}"
  description = "HTTP from the internet to the app instance"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Installing Docker and pulling the image go out through the public IP.
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "sbh-workload-demo-sg-ec2-${var.application_id}" }
}

resource "aws_instance" "app" {
  ami                         = data.aws_ssm_parameter.ami.insecure_value
  instance_type               = var.instance_type
  subnet_id                   = var.public_subnet_ids[0]
  vpc_security_group_ids      = [aws_security_group.instance.id]
  iam_instance_profile        = aws_iam_instance_profile.instance.name
  associate_public_ip_address = true

  # IMDSv2 only.
  metadata_options {
    http_tokens = "required"
  }

  # Retries the pull because the instance role can take a few seconds to work after boot.
  user_data = <<-EOT
    #!/bin/bash
    set -eux
    dnf install -y docker
    systemctl enable --now docker
    for i in $(seq 1 30); do
      aws ecr get-login-password --region ${var.region} | docker login --username AWS --password-stdin ${local.registry} \
        && docker pull ${var.image} && break
      sleep 5
    done
    docker run -d --name app --restart always -p 80:${var.container_port} -e PORT=${var.container_port} ${var.image}
  EOT

  user_data_replace_on_change = true

  tags = { Name = local.name, DeploymentId = var.deployment_id }

  depends_on = [aws_iam_role_policy_attachment.ecr]
}
