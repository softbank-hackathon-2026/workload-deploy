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
  description = "Container image with the Lambda Web Adapter added by the pipeline, pinned by digest (<repository>@sha256:<digest>)."
  type        = string

  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.image))
    error_message = "image must be pinned by digest."
  }
}

# Filled per app (by AI later, fixed defaults for now).

variable "container_port" {
  description = "Port the web server listens on inside the image. The adapter forwards requests to it."
  type        = number
  default     = 8080

  validation {
    condition     = var.container_port >= 1 && var.container_port <= 65535 && floor(var.container_port) == var.container_port
    error_message = "container_port must be an integer between 1 and 65535."
  }
}

variable "memory" {
  description = "Lambda memory (MiB). CPU grows with memory."
  type        = number
  default     = 512

  validation {
    condition     = var.memory >= 128 && var.memory <= 10240 && floor(var.memory) == var.memory
    error_message = "memory must be an integer between 128 and 10240."
  }
}

variable "timeout" {
  description = "Seconds one request may run."
  type        = number
  default     = 30

  validation {
    condition     = var.timeout >= 1 && var.timeout <= 900 && floor(var.timeout) == var.timeout
    error_message = "timeout must be an integer between 1 and 900."
  }
}

variable "health_check_path" {
  description = "Path the adapter waits on before the first request, and the pipeline checks after deploy. Any 2xx or 3xx response is healthy."
  type        = string
  default     = "/"

  validation {
    condition     = can(regex("^/[A-Za-z0-9._~/-]{0,254}$", var.health_check_path))
    error_message = "health_check_path must start with / and use only URL path characters."
  }
}
