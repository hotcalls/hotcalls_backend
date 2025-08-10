# Basic configuration
variable "namespace_name" {
  description = "Name of the Kubernetes namespace"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

# Container configuration
variable "container_registry" {
  description = "Container registry URL"
  type        = string
}

variable "image_tag" {
  description = "Image tag for containers"
  type        = string
  default     = "latest"
}

variable "backend_replicas" {
  description = "Number of backend replicas"
  type        = number
  default     = 1
}

variable "frontend_replicas" {
  description = "Number of frontend replicas"
  type        = number
  default     = 1
}

# Database configuration
variable "db_name" {
  description = "Database name"
  type        = string
}

variable "db_user" {
  description = "Database user"
  type        = string
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "db_host" {
  description = "Database host"
  type        = string
}

# Redis configuration
variable "redis_password" {
  description = "Redis password"
  type        = string
  sensitive   = true
}

# Storage configuration
variable "storage_account_name" {
  description = "Azure storage account name"
  type        = string
}

variable "storage_account_key" {
  description = "Azure storage account key"
  type        = string
  sensitive   = true
}

# Application configuration
variable "secret_key" {
  description = "Django secret key"
  type        = string
  sensitive   = true
}

variable "debug" {
  description = "Django debug setting"
  type        = string
  default     = "False"
}

variable "cors_allow_all_origins" {
  description = "CORS allow all origins"
  type        = string
  default     = "False"
}

variable "base_url" {
  description = "Base URL for the application"
  type        = string
}

# Email configuration
variable "email_host" {
  description = "Email host"
  type        = string
}

variable "email_port" {
  description = "Email port"
  type        = string
}

variable "email_use_tls" {
  description = "Email use TLS"
  type        = string
}

variable "email_use_ssl" {
  description = "Email use SSL"
  type        = string
}

variable "email_host_user" {
  description = "Email host user"
  type        = string
  sensitive   = true
}

variable "email_host_password" {
  description = "Email host password"
  type        = string
  sensitive   = true
}

variable "default_from_email" {
  description = "Default from email"
  type        = string
}

variable "server_email" {
  description = "Server email"
  type        = string
}

# Static IP configuration
variable "static_ip_address" {
  description = "Static IP address for the ingress controller"
  type        = string
} 