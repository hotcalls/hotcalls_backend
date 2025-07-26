# Project Configuration - Dynamic Environment
project_name    = "hotcalls"
environment     = "dev"  # Can be: dev, staging, prod
location        = "West Europe"

# Networking
vnet_address_space     = ["10.0.0.0/16"]
aks_subnet_cidr        = "10.0.1.0/24"
app_gateway_subnet_cidr = "10.0.2.0/24"
private_endpoint_subnet_cidr = "10.0.3.0/24"

# AKS Configuration - DEV sizing (small/cheap)
aks_node_count         = 1
aks_node_size          = "Standard_B2s"  # Small nodes for dev
aks_max_node_count     = 2  # Limited scaling for dev
aks_min_node_count     = 1
kubernetes_version     = "1.28"

# Database Configuration - DEV sizing (minimal)
postgres_version       = "14"
postgres_sku_name     = "B_Standard_B1ms"  # Smallest burstable SKU
postgres_storage_mb   = 32768  # 32GB minimum
postgres_admin_username = "hotcallsadmin"

# Application Configuration
app_image_tag         = "latest"
app_replica_count     = 2

# Storage Configuration
storage_account_tier  = "Standard"
storage_replication_type = "LRS"

# Monitoring Configuration
log_analytics_sku     = "PerGB2018"
log_retention_days    = 30
enable_monitoring_alerts = true
alert_email_addresses = ["einfach@malmachen.com"]

# API Management (disabled for initial deployment)
enable_api_management = false
api_management_sku    = "Developer_1"
api_management_publisher_email = "einfach@malmachen.com"

# Tags - Dynamic based on environment variable
tags = {
  Project     = "HotCalls"
  Environment = "Development"  # Will be overridden by environment
  Owner       = "einfach@malmachen.com"
  ManagedBy   = "Terraform"
} 