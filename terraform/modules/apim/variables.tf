variable "enable_apim" {
  description = "Whether to enable API Management"
  type        = bool
  default     = false
}

variable "apim_name" {
  description = "Name of the API Management instance"
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

variable "publisher_name" {
  description = "Publisher name for API Management"
  type        = string
  default     = "HotCalls"
}

variable "publisher_email" {
  description = "Publisher email for API Management"
  type        = string
}

variable "sku_name" {
  description = "SKU for API Management"
  type        = string
  default     = "Developer_1"
}

variable "backend_service_url" {
  description = "URL of the backend service"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
} 