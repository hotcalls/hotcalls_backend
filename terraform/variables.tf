# Core variables
variable "project_name" {
  description = "Name of the project, used as prefix for resource names"
  type        = string
  default     = "hotcalls"
  
  validation {
    condition     = can(regex("^[a-zA-Z0-9-]+$", var.project_name))
    error_message = "Project name must contain only alphanumeric characters and hyphens."
  }
}

variable "environment" {
  description = "Environment name (development, staging, production)"
  type        = string
  default     = "development"
  
  validation {
    condition     = can(regex("^(development|staging|production)(-index-[0-9]+)?$", var.environment))
    error_message = "Environment must be one of: development, staging, production, or with index suffix like staging-index-1."
  }
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "West Europe"
}

variable "location_short" {
  description = "Short name for Azure region (used in resource naming)"
  type        = string
  default     = "we"
}

# Network variables
variable "vnet_address_space" {
  description = "Address space for the virtual network"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "aks_subnet_address_prefix" {
  description = "Address prefix for the AKS subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "app_gateway_subnet_address_prefix" {
  description = "Address prefix for the Application Gateway subnet"
  type        = string
  default     = "10.0.2.0/24"
}

variable "private_endpoint_subnet_address_prefix" {
  description = "Address prefix for the private endpoints subnet"
  type        = string
  default     = "10.0.3.0/24"
}

# AKS variables
variable "aks_node_count" {
  description = "Number of nodes in the AKS default node pool"
  type        = number
  default     = 2
}

variable "aks_node_size" {
  description = "Size of the AKS nodes"
  type        = string
  default     = "Standard_D2s_v3"
}

variable "aks_max_node_count" {
  description = "Maximum number of nodes for autoscaling"
  type        = number
  default     = 10
}

variable "aks_min_node_count" {
  description = "Minimum number of nodes for autoscaling"
  type        = number
  default     = 1
}

# Database variables
variable "postgres_sku_name" {
  description = "SKU name for PostgreSQL flexible server"
  type        = string
  default     = "B_Standard_B1ms"
}

variable "postgres_storage_mb" {
  description = "Storage size in MB for PostgreSQL"
  type        = number
  default     = 32768 # 32GB
}

variable "postgres_backup_retention_days" {
  description = "Backup retention period in days"
  type        = number
  default     = 7
}

variable "postgres_version" {
  description = "PostgreSQL version"
  type        = string
  default     = "15"
}

# Application variables
variable "django_secret_key" {
  description = "Django secret key"
  type        = string
  sensitive   = true
  default     = null
}

variable "postgres_admin_username" {
  description = "PostgreSQL administrator username"
  type        = string
  default     = "hotcalls_admin"
  sensitive   = true
}

variable "postgres_admin_password" {
  description = "PostgreSQL administrator password"
  type        = string
  sensitive   = true
  default     = null
}

# Storage variables
variable "storage_account_tier" {
  description = "Storage account tier"
  type        = string
  default     = "Standard"
}

variable "storage_account_replication_type" {
  description = "Storage account replication type"
  type        = string
  default     = "LRS"
}

# API Management variables
variable "apim_sku_name" {
  description = "API Management SKU name"
  type        = string
  default     = "Developer_1"
}

variable "apim_publisher_name" {
  description = "API Management publisher name"
  type        = string
  default     = "HotCalls"
}

variable "apim_publisher_email" {
  description = "API Management publisher email"
  type        = string
  default     = "admin@hotcalls.com"
}

variable "backend_internal_url" {
  description = "Cluster-internal URL of the backend service to be exposed through API Management"
  type        = string
  default     = ""
}

# Domain and DNS variables
variable "custom_domain" {
  description = "Custom domain for the application (optional)"
  type        = string
  default     = null
}

variable "enable_cdn" {
  description = "Enable CDN for static content"
  type        = bool
  default     = true
}

# Monitoring variables
variable "enable_application_insights" {
  description = "Enable Application Insights"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "Log retention period in days"
  type        = number
  default     = 30
}

# New variables (added to align with terraform.tfvars)

variable "log_analytics_sku" {
  description = "SKU tier for Log Analytics workspace"
  type        = string
  default     = "PerGB2018"
}

variable "app_image_tag" {
  description = "Docker image tag for application deployments"
  type        = string
  default     = "latest"
}

variable "app_replica_count" {
  description = "Number of application replicas"
  type        = number
  default     = 1
}

# Tags
variable "default_tags" {
  description = "Default tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "HotCalls"
    ManagedBy   = "Terraform"
    Repository  = "hotcalls"
  }
} 

variable "tags" {
  description = "A map of tags to assign to the resources"
  type        = map(string)
  default = {
    Project     = "HotCalls"
    ManagedBy   = "Terraform"
    Repository  = "hotcalls"
  }
}

# Additional missing variables
variable "kubernetes_version" {
  description = "Kubernetes version for AKS"
  type        = string
  default     = "1.28"
}

variable "alert_email_addresses" {
  description = "Email addresses for alerts"
  type        = list(string)
  default     = []
}

variable "enable_api_management" {
  description = "Enable API Management service"
  type        = bool
  default     = false
}

variable "enable_monitoring_alerts" {
  description = "Enable monitoring alerts"
  type        = bool
  default     = true
} 