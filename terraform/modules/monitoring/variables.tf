variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "log_analytics_name" {
  description = "Name of the Log Analytics workspace"
  type        = string
}

variable "app_insights_name" {
  description = "Name of the Application Insights instance"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "log_analytics_sku" {
  description = "SKU for Log Analytics workspace"
  type        = string
  default     = "PerGB2018"
}

variable "retention_days" {
  description = "Number of days to retain logs"
  type        = number
  default     = 30
}

variable "aks_cluster_id" {
  description = "ID of the AKS cluster"
  type        = string
}

variable "enable_alerts" {
  description = "Whether to enable metric alerts"
  type        = bool
  default     = true
}

variable "alert_email_addresses" {
  description = "List of email addresses for alerts"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
} 