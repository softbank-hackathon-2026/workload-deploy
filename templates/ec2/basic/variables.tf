# Set by the pipeline.

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "application_id" {
  description = "App Space ID."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]{1,24}$", var.application_id))
    error_message = "application_id must be 1-24 lowercase letters, digits or hyphens."
  }
}

variable "deployment_id" {
  type = string

  validation {
    condition     = can(regex("^[a-z0-9-]{1,64}$", var.deployment_id))
    error_message = "deployment_id must be lowercase letters, digits or hyphens."
  }
}

variable "infra_id" {
  type = string
}

variable "image" {
  description = "Container image in the Workload ECR, pinned by digest (<registry>/<repository>@sha256:<digest>)."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$", var.image))
    error_message = "image must be an ECR image pinned by digest."
  }
}

# Set by the Infra Space (infra values in the backend's GET /api/plans/{plan_id} response).

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  description = "Public subnets of the Space. The instance goes in the first one."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_ids) >= 1
    error_message = "At least one public subnet is needed."
  }
}

# Filled per app (by AI later, fixed defaults for now).

variable "container_port" {
  description = "Port the app listens on inside the container. The instance serves it on port 80."
  type        = number
  default     = 80

  validation {
    condition     = var.container_port >= 1 && var.container_port <= 65535 && floor(var.container_port) == var.container_port
    error_message = "container_port must be an integer between 1 and 65535."
  }
}

variable "instance_type" {
  description = "Server size. Limited to small burstable types to keep the demo budget."
  type        = string
  default     = "t3.micro"

  validation {
    condition     = contains(["t3.micro", "t3.small", "t3.medium"], var.instance_type)
    error_message = "instance_type must be t3.micro, t3.small or t3.medium."
  }
}

variable "health_check_path" {
  description = "HTTP path the pipeline checks after deploy. Any 2xx or 3xx response is healthy."
  type        = string
  default     = "/"

  validation {
    condition     = can(regex("^/[A-Za-z0-9._~/-]{0,254}$", var.health_check_path))
    error_message = "health_check_path must start with / and use only URL path characters."
  }
}
