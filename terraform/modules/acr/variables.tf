variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region for resources"
  type        = string
}

variable "name" {
  description = "Name of the Azure Container Registry"
  type        = string
}

variable "sku" {
  description = "SKU tier for the Container Registry"
  type        = string
  default     = "Standard"
  
  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.sku)
    error_message = "SKU must be one of: Basic, Standard, Premium."
  }
}

variable "admin_enabled" {
  description = "Enable admin user for the Container Registry"
  type        = bool
  default     = true
}

variable "public_network_access_enabled" {
  description = "Enable public network access"
  type        = bool
  default     = true
}

variable "network_rule_set_enabled" {
  description = "Enable network rule set restrictions"
  type        = bool
  default     = false
}

variable "allowed_ip_ranges" {
  description = "List of allowed IP ranges for registry access"
  type        = list(string)
  default     = []
}

variable "allowed_subnet_ids" {
  description = "List of allowed subnet IDs for registry access"
  type        = list(string)
  default     = []
}

variable "trust_policy_enabled" {
  description = "Enable content trust policy"
  type        = bool
  default     = false
}

variable "retention_policy_enabled" {
  description = "Enable retention policy for untagged manifests"
  type        = bool
  default     = true
}

variable "retention_days" {
  description = "Number of days to retain untagged manifests"
  type        = number
  default     = 30
}

variable "quarantine_policy_enabled" {
  description = "Enable quarantine policy"
  type        = bool
  default     = false
}

variable "zone_redundancy_enabled" {
  description = "Enable zone redundancy (Premium SKU only)"
  type        = bool
  default     = false
}

variable "export_policy_enabled" {
  description = "Enable export policy (Premium SKU only)"
  type        = bool
  default     = true
}

variable "data_endpoint_enabled" {
  description = "Enable data endpoint (Premium SKU only)"
  type        = bool
  default     = false
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