# Set by the pipeline.

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "application_id" {
  description = "App Space ID. Up to 24 characters so ALB and target group names stay within 32."
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
  description = "Container image pinned by digest (<repository>@sha256:<digest>)."
  type        = string

  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.image))
    error_message = "image must be pinned by digest."
  }
}

# Set by the Infra Space (infra values in the backend's GET /api/plans/{plan_id} response).

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  description = "Public subnets in two AZs. Tasks get public IPs because the public Space has no NAT."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_ids) >= 2
    error_message = "The ALB needs public subnets in at least two AZs."
  }
}

# Filled per app (by AI later, fixed defaults for now).

variable "container_port" {
  description = "Port the app listens on inside the container."
  type        = number
  default     = 80

  validation {
    condition     = var.container_port >= 1 && var.container_port <= 65535 && floor(var.container_port) == var.container_port
    error_message = "container_port must be an integer between 1 and 65535."
  }
}

variable "cpu" {
  description = "Fargate CPU units."
  type        = number
  default     = 256

  validation {
    condition     = contains([256, 512, 1024], var.cpu)
    error_message = "cpu must be 256, 512 or 1024."
  }
}

variable "memory" {
  description = "Fargate memory (MiB). Must be a valid combination with cpu."
  type        = number
  default     = 512

  validation {
    condition = contains(lookup({
      256  = [512, 1024, 2048]
      512  = [1024, 2048, 3072, 4096]
      1024 = [2048, 3072, 4096, 5120, 6144, 7168, 8192]
    }, tostring(var.cpu), []), var.memory)
    error_message = "memory is not a valid Fargate combination for this cpu."
  }
}

variable "health_check_path" {
  description = "HTTP path the load balancer checks. Any 2xx or 3xx response is healthy."
  type        = string
  default     = "/"

  validation {
    condition     = can(regex("^/[A-Za-z0-9._~/-]{0,254}$", var.health_check_path))
    error_message = "health_check_path must start with / and use only URL path characters."
  }
}
