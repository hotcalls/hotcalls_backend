variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region for resources"
  type        = string
}

variable "name" {
  description = "Name of the PostgreSQL server"
  type        = string
}

variable "admin_username" {
  description = "Administrator username for PostgreSQL"
  type        = string
  sensitive   = true
}

variable "admin_password" {
  description = "Administrator password for PostgreSQL"
  type        = string
  sensitive   = true
}

variable "postgres_version" {
  description = "PostgreSQL version"
  type        = string
  default     = "15"
  
  validation {
    condition     = contains(["11", "12", "13", "14", "15"], var.postgres_version)
    error_message = "PostgreSQL version must be one of: 11, 12, 13, 14, 15."
  }
}

variable "sku_name" {
  description = "SKU name for the PostgreSQL server"
  type        = string
  default     = "B_Standard_B1ms"
}

variable "storage_mb" {
  description = "Storage size in MB"
  type        = number
  default     = 32768
  
  validation {
    condition     = var.storage_mb >= 32768 && var.storage_mb <= 16777216
    error_message = "Storage size must be between 32768 MB (32 GB) and 16777216 MB (16 TB)."
  }
}

variable "backup_retention_days" {
  description = "Backup retention period in days"
  type        = number
  default     = 7
  
  validation {
    condition     = var.backup_retention_days >= 7 && var.backup_retention_days <= 35
    error_message = "Backup retention days must be between 7 and 35."
  }
}

variable "geo_redundant_backup_enabled" {
  description = "Enable geo-redundant backups"
  type        = bool
  default     = false
}

variable "virtual_network_id" {
  description = "ID of the virtual network"
  type        = string
}

variable "private_endpoint_subnet_id" {
  description = "ID of the subnet for private endpoints"
  type        = string
}

variable "delegated_subnet_id" {
  description = "ID of the delegated subnet for PostgreSQL"
  type        = string
  default     = null
}

variable "high_availability_enabled" {
  description = "Enable high availability"
  type        = bool
  default     = false
}

variable "standby_availability_zone" {
  description = "Availability zone for standby server"
  type        = string
  default     = null
}

variable "maintenance_window" {
  description = "Maintenance window configuration"
  type = object({
    day_of_week  = number
    start_hour   = number
    start_minute = number
  })
  default = {
    day_of_week  = 0  # Sunday
    start_hour   = 1  # 1 AM
    start_minute = 0
  }
}

variable "azure_ad_auth_enabled" {
  description = "Enable Azure Active Directory authentication"
  type        = bool
  default     = false
}

variable "tenant_id" {
  description = "Azure AD tenant ID"
  type        = string
  default     = null
}

variable "database_name" {
  description = "Name of the database to create"
  type        = string
  default     = "hotcalls"
}

variable "enable_extensions" {
  description = "Enable PostgreSQL extensions"
  type        = bool
  default     = true
}

variable "allowed_ip_ranges" {
  description = "List of allowed IP ranges for direct access"
  type        = list(string)
  default     = []
}

variable "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace for diagnostics"
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

# Application user configuration
variable "app_user_name" {
  description = "Application database user name"
  type        = string
  default     = null
}

variable "app_user_password" {
  description = "Application database user password"
  type        = string
  sensitive   = true
  default     = null
} 