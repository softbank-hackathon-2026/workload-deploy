terraform {
  required_version = ">= 1.11.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.24, < 7.0"
    }
  }

  # Bucket and key are passed at init: -backend-config=bucket=... -backend-config=key=apps/<application_id>/terraform.tfstate
  backend "s3" {
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  # ADR-005 required tags. DeploymentId changes every deploy, so it is set only on the task definition and service.
  default_tags {
    tags = {
      Project       = "SBH"
      Scope         = "workload"
      Environment   = "demo"
      ManagedBy     = "terraform"
      Owner         = "박소정"
      ApplicationId = var.application_id
      InfraId       = var.infra_id
    }
  }
}
