variable "environment" {
  description = "dev or prod"
  type        = string
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod"
  }
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus2"
}

variable "workload" {
  description = "Short workload name used in resource names"
  type        = string
  default     = "lcdesk"
}

variable "image" {
  description = "Agent Server image built with `langgraph build` and pushed to the registry"
  type        = string
  default     = "mcr.microsoft.com/k8se/quickstart:latest"
}

variable "private_networking" {
  description = "VNet-integrated Container Apps environment (internal ingress), private Postgres and private endpoints for Redis and Key Vault"
  type        = bool
  default     = false
}

variable "min_replicas" {
  description = "Agent Server replicas kept running (the server runs background workers; scale-to-zero is not recommended)"
  type        = number
  default     = 1
  validation {
    condition     = var.min_replicas >= 1
    error_message = "min_replicas must be at least 1"
  }
}

variable "max_replicas" {
  type    = number
  default = 3
}

variable "postgres_sku" {
  type    = string
  default = "B_Standard_B1ms"
}

variable "postgres_storage_mb" {
  type    = number
  default = 32768
}

variable "redis_sku" {
  description = "Basic, Standard or Premium"
  type        = string
  default     = "Basic"
}

variable "langsmith_endpoint" {
  type    = string
  default = "https://api.smith.langchain.com"
}

variable "vnet_address_space" {
  type    = string
  default = "10.40.0.0/16"
}

variable "tags" {
  type    = map(string)
  default = {}
}
