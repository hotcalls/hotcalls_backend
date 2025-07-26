# Development Environment Configuration
# Copy this file and update values for your Azure environment

# Project Configuration
project_name    = "hotcalls"
environment     = "dev"
location        = "North Europe"

location_short  = "ne"

# Your email for alerts and API Management
alert_email_addresses = ["einfach@malmachen.com"]
apim_publisher_email  = "einfach@malmachen.com"

# Networking (can keep defaults)
vnet_address_space           = ["10.0.0.0/16"]
aks_subnet_address_prefix             = "10.0.1.0/24"
app_gateway_subnet_address_prefix     = "10.0.2.0/24"
private_endpoint_subnet_address_prefix = "10.0.3.0/24"

# AKS Configuration (small for dev)
aks_node_count         = 1
aks_node_size          = "Standard_B2pls_v2"
aks_max_node_count     = 2
aks_min_node_count     = 1
kubernetes_version     = "1.28"

# Database Configuration (minimal for dev)
postgres_version       = "14"
postgres_sku_name     = "GP_Standard_D2s_v3"
postgres_storage_mb   = 32768
postgres_admin_username = "hotcallsadmin"
# NOTE: postgres_admin_password will be auto-generated

# Storage Configuration
storage_account_tier         = "Standard"
storage_account_replication_type = "LRS"

# Application Configuration
app_image_tag         = "latest"
app_replica_count     = 1

# Features (disabled for dev to save costs)
enable_api_management = false
apim_sku_name = "Developer_1"
enable_monitoring_alerts = true
log_retention_days    = 7  # Short retention for dev

# Tags
tags = {
  Project     = "HotCalls"
  Environment = "Development"
  Owner       = "einfach@malmachen.com"
  ManagedBy   = "Terraform"
  Purpose     = "Development"
} 