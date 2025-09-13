# Production Environment Configuration
# This configuration creates new production resources

# Project Configuration
project_name    = "messecaller"
environment     = "production"
location        = "North Europe"
location_short  = "ne"

# Resource group will be created by Terraform
resource_group_name = ""

# Your email for alerts and API Management
alert_email_addresses = ["einfach@malmachen.com"]
apim_publisher_email  = "einfach@malmachen.com"

# Networking (can keep defaults)
vnet_address_space           = ["10.0.0.0/16"]
aks_subnet_address_prefix             = "10.0.1.0/24"
app_gateway_subnet_address_prefix     = "10.0.2.0/24"
private_endpoint_subnet_address_prefix = "10.0.3.0/24"

# AKS Configuration (production ready)
aks_node_count         = 2
aks_node_size          = "Standard_D2as_v5"
aks_max_node_count     = 3
aks_min_node_count     = 1
kubernetes_version     = "1.28"

# Database Configuration (production ready)
postgres_version       = "14"
postgres_sku_name     = "GP_Standard_D2s_v3"
postgres_storage_mb   = 32768
postgres_admin_username = "postgres"
# NOTE: postgres_admin_password matches .env DB_PASSWORD

# Storage Configuration
storage_account_tier         = "Standard"
storage_account_replication_type = "LRS"

# Application Configuration
app_image_tag         = "latest"
app_replica_count     = 1

# Features (can be selectively enabled for staging)
enable_api_management = false
backend_internal_url  = "http://hotcalls-backend-service.hotcalls-staging.svc.cluster.local"
apim_sku_name = "Developer_1"
enable_monitoring_alerts = true
log_retention_days    = 30  # Minimum for Log Analytics

# Database and Application Secrets
app_db_name = "hotcalls_db"
app_db_user = "postgres"
app_db_password = "tXaxzxWY@8LqHDJxc9_Myom@xBp@U9XgpDjn-dV."
app_secret_key = "J0FBtEwFgoUiec5bQwzvGUFzN-QYBPf_7g7bcOap6NE"
app_redis_password = "3E1_mH8bD9Rp5GQKpOUv5A"

# Application settings
app_debug = "False"
app_cors_allow_all = "False"
app_base_url = "https://app.messecaller.ai"

# Email configuration (update with your SMTP settings)
app_email_host = "smtp.gmail.com"
app_email_port = "587"
app_email_use_tls = "True"
app_email_use_ssl = "False"
app_email_host_user = "einfach@malmachen.com"
app_email_host_password = ""  # Set your email password
app_default_from_email = "einfach@malmachen.com"
app_server_email = "einfach@malmachen.com"

# Tags
tags = {
  Project     = "MesseCaller"
  Environment = "Production"
  Owner       = "einfach@malmachen.com"
  ManagedBy   = "Terraform"
  Purpose     = "Production"
} 