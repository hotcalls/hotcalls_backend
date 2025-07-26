# Project Configuration - Dynamic Environment
project_name    = "hotcalls"
environment     = "staging"  # Can be: development, staging, production
location        = "North Europe"

# Short location code used in resource names
location_short  = "ne"
# Networking
vnet_address_space     = ["10.0.0.0/16"]
aks_subnet_address_prefix        = "10.0.1.0/24"
app_gateway_subnet_address_prefix = "10.0.2.0/24"
private_endpoint_subnet_address_prefix = "10.0.3.0/24"

# AKS Configuration - DEV sizing (small/cheap)
aks_node_count         = 1
aks_node_size          = "Standard_B2pls_v2"  # Allowed burstable v2 size in GWC
aks_max_node_count     = 2  # Limited scaling for dev
aks_min_node_count     = 1
kubernetes_version     = "1.28"

# Database Configuration - DEV sizing (minimal)
postgres_version       = "14"
postgres_sku_name     = "GP_Standard_D2s_v3"  # General Purpose D2s_v3 supported in GWC
postgres_storage_mb   = 32768  # 32GB minimum
postgres_admin_username = "hotcallsadmin"

# Application Configuration
app_image_tag         = "latest"
app_replica_count     = 2

# Storage Configuration
storage_account_tier  = "Standard"
storage_account_replication_type = "LRS"

# Monitoring Configuration
log_analytics_sku     = "PerGB2018"
log_retention_days    = 30
enable_monitoring_alerts = true
alert_email_addresses = ["einfach@malmachen.com"]

# API Management (disabled for initial deployment)
enable_api_management = false
apim_sku_name    = "Developer_1"
apim_publisher_email = "einfach@malmachen.com"

# Tags - Dynamic based on environment variable
tags = {
  Project     = "HotCalls"
  Environment = "Staging"  # Will be overridden by environment
  Owner       = "einfach@malmachen.com"
  ManagedBy   = "Terraform"
} 