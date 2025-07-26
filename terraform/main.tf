# Data sources
data "azurerm_client_config" "current" {}

# Generate random strings for unique resource names
resource "random_string" "unique_id" {
  length  = 8
  upper   = false
  special = false
}

resource "random_password" "postgres_admin_password" {
  count   = var.postgres_admin_password == null ? 1 : 0
  length  = 16
  special = true
}

resource "random_password" "django_secret_key" {
  count   = var.django_secret_key == null ? 1 : 0
  length  = 50
  special = true
}

# Local variables
locals {
  # Resource naming
  resource_prefix = "${var.project_name}-${var.environment}-${var.location_short}"
  unique_suffix   = random_string.unique_id.result
  
  # Common tags
  common_tags = merge(var.default_tags, {
    Environment = var.environment
    Location    = var.location
  })
  
  # Generated secrets
  postgres_password = var.postgres_admin_password != null ? var.postgres_admin_password : random_password.postgres_admin_password[0].result
  django_secret     = var.django_secret_key != null ? var.django_secret_key : random_password.django_secret_key[0].result
}

# Resource Group
resource "azurerm_resource_group" "main" {
  name     = "${local.resource_prefix}-rg"
  location = var.location
  tags     = local.common_tags
}

# Network module
module "network" {
  source = "./modules/network"
  
  resource_group_name                      = azurerm_resource_group.main.name
  location                                = var.location
  resource_prefix                         = local.resource_prefix
  
  vnet_address_space                      = var.vnet_address_space
  aks_subnet_address_prefix               = var.aks_subnet_address_prefix
  app_gateway_subnet_address_prefix       = var.app_gateway_subnet_address_prefix
  private_endpoint_subnet_address_prefix  = var.private_endpoint_subnet_address_prefix
  
  tags = local.common_tags
}

# Azure Container Registry
module "acr" {
  source = "./modules/acr"
  
  resource_group_name = azurerm_resource_group.main.name
  location           = var.location
  name               = "${local.resource_prefix}-acr-${local.unique_suffix}"
  
  tags = local.common_tags
}

# Azure Kubernetes Service
module "aks" {
  source = "./modules/aks"
  
  resource_group_name = azurerm_resource_group.main.name
  location           = var.location
  name               = "${local.resource_prefix}-aks"
  
  vnet_subnet_id     = module.network.aks_subnet_id
  acr_id             = module.acr.registry_id
  
  node_count         = var.aks_node_count
  node_size          = var.aks_node_size
  max_node_count     = var.aks_max_node_count
  min_node_count     = var.aks_min_node_count
  
  tags = local.common_tags
  
  depends_on = [module.network, module.acr]
}

# PostgreSQL Database
module "postgres" {
  source = "./modules/postgres"
  
  resource_group_name = azurerm_resource_group.main.name
  location           = var.location
  name               = "${local.resource_prefix}-postgres"
  
  admin_username = var.postgres_admin_username
  admin_password = local.postgres_password
  
  sku_name               = var.postgres_sku_name
  storage_mb             = var.postgres_storage_mb
  backup_retention_days  = var.postgres_backup_retention_days
  postgres_version       = var.postgres_version
  
  virtual_network_id         = module.network.vnet_id
  private_endpoint_subnet_id = module.network.private_endpoint_subnet_id
  
  tags = local.common_tags
  
  depends_on = [module.network]
}

# Key Vault
module "keyvault" {
  source = "./modules/keyvault"
  
  resource_group_name = azurerm_resource_group.main.name
  location           = var.location
  name               = "${local.resource_prefix}-kv-${local.unique_suffix}"
  
  tenant_id = data.azurerm_client_config.current.tenant_id
  
  # Grant access to AKS managed identity
  aks_principal_id = module.aks.principal_id
  
  # Store application secrets
  secrets = {
    "django-secret-key"        = local.django_secret
    "postgres-admin-username"  = var.postgres_admin_username
    "postgres-admin-password"  = local.postgres_password
    "postgres-connection-string" = module.postgres.connection_string
  }
  
  virtual_network_id         = module.network.vnet_id
  private_endpoint_subnet_id = module.network.private_endpoint_subnet_id
  
  tags = local.common_tags
  
  depends_on = [module.network, module.aks, module.postgres]
}

# Storage Account
module "storage" {
  source = "./modules/storage"
  
  storage_account_name = "${var.project_name}${var.environment}st${local.unique_suffix}"
  resource_group_name  = azurerm_resource_group.main.name
  location            = var.location
  
  account_tier       = var.storage_account_tier
  replication_type   = var.storage_account_replication_type
  
  private_endpoint_enabled   = false  # Simplified for dev
  private_endpoint_subnet_id = ""
  
  tags = local.common_tags
  
  depends_on = [module.network]
}

# API Management
module "apim" {
  source = "./modules/apim"
  
  enable_apim         = var.enable_api_management
  apim_name          = "${local.resource_prefix}-apim"
  resource_group_name = azurerm_resource_group.main.name
  location           = var.location
  
  sku_name         = var.apim_sku_name
  publisher_name   = var.apim_publisher_name
  publisher_email  = var.apim_publisher_email
  
  backend_service_url = ""  # Will be set after AKS deployment
  
  tags = local.common_tags
  
  depends_on = [module.network]
}

# Monitoring
module "monitoring" {
  source = "./modules/monitoring"
  
  project_name        = var.project_name
  log_analytics_name  = "${local.resource_prefix}-logs"
  app_insights_name   = "${local.resource_prefix}-appinsights"
  resource_group_name = azurerm_resource_group.main.name
  location           = var.location
  
  enable_alerts         = var.enable_monitoring_alerts
  retention_days        = var.log_retention_days
  alert_email_addresses = var.alert_email_addresses
  
  # Connect to AKS for container insights
  aks_cluster_id = module.aks.cluster_id
  
  tags = local.common_tags
  
  depends_on = [module.aks]
} 