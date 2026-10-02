# Set by the pipeline.

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "application_id" {
  description = "App Space ID. Up to 24 characters so the target group name stays within 32."
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

variable "private_subnet_ids" {
  description = "App subnets (private) in two AZs. Tasks get no public IP and pull the image through the Space's NAT."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Tasks need private subnets in at least two AZs."
  }
}

variable "alb_listener_arn" {
  description = "HTTPS listener of the Space's shared ALB. The app adds one path rule to it."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:elasticloadbalancing:[a-z0-9-]+:[0-9]{12}:listener/app/", var.alb_listener_arn))
    error_message = "alb_listener_arn must be an application load balancer listener ARN."
  }
}

variable "alb_security_group_id" {
  description = "Security group of the shared ALB. Only it may reach the tasks."
  type        = string
}

variable "alb_base_url" {
  description = "Public address of the shared ALB, e.g. https://demo.howon.me (no trailing slash)."
  type        = string

  validation {
    condition     = can(regex("^https?://[a-z0-9.-]+$", var.alb_base_url))
    error_message = "alb_base_url must be scheme and host only, like https://demo.howon.me."
  }
}

# Set by the backend per app (not by AI): where the app sits on the shared address.

variable "path_pattern" {
  description = "Paths this app serves on the shared ALB, e.g. /api/* or /*."
  type        = string
  default     = "/*"

  validation {
    condition     = can(regex("^/[A-Za-z0-9._~/-]*[*]?$", var.path_pattern))
    error_message = "path_pattern must start with / and may end with *."
  }
}

variable "rule_priority" {
  description = "Listener rule priority. The ALB checks lower numbers first, so a narrower path (/api/*) needs a lower number than /*."
  type        = number

  validation {
    condition     = var.rule_priority >= 1 && var.rule_priority <= 50000 && floor(var.rule_priority) == var.rule_priority
    error_message = "rule_priority must be an integer between 1 and 50000."
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
  description = "HTTP path the target group checks and the pipeline calls through the shared address. Must fall under path_pattern (e.g. /api/health for /api/*). Any 2xx or 3xx response is healthy."
  type        = string
  default     = "/"

  validation {
    condition     = can(regex("^/[A-Za-z0-9._~/-]{0,254}$", var.health_check_path))
    error_message = "health_check_path must start with / and use only URL path characters."
  }

  # The pipeline checks this path through the shared address; outside path_pattern it would reach another app.
  validation {
    condition     = endswith(var.path_pattern, "*") ? startswith(var.health_check_path, trimsuffix(var.path_pattern, "*")) : var.health_check_path == var.path_pattern
    error_message = "health_check_path must fall under path_pattern (e.g. /api/health for /api/*)."
  }
}
