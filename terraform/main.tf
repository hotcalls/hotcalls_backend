# Data sources
data "azurerm_client_config" "current" {}

# Generate random strings for unique resource names
resource "random_string" "unique_id" {
  length  = 8
  upper   = false
  special = false
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
}

# Resource Group
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name != "" ? var.resource_group_name : "${local.resource_prefix}-rg"
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
  location            = var.location
  name = lower(substr(replace("${local.resource_prefix}acr${local.unique_suffix}", "-", ""), 0, 50))
  
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

# PostgreSQL Database - SIMPLIFIED WITHOUT PRIVATE ENDPOINT FOR NOW
resource "azurerm_postgresql_flexible_server" "main" {
  name                = "${local.resource_prefix}-postgres"
  resource_group_name = azurerm_resource_group.main.name
  location           = var.location
  
  administrator_login    = var.app_db_user
  administrator_password = var.app_db_password
  
  sku_name = var.postgres_sku_name
  storage_mb = var.postgres_storage_mb
  version = var.postgres_version
  zone = "1"
  
  backup_retention_days = var.postgres_backup_retention_days
  
  # Use public access for simplicity
  public_network_access_enabled = true
  
  tags = local.common_tags
}

# Allow Azure services to access PostgreSQL
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# PostgreSQL Database
resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = var.app_db_name
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "utf8"
}

# Storage Account
module "storage" {
  source = "./modules/storage"
  
  storage_account_name = lower(substr("${var.storage_account_prefix != "" ? var.storage_account_prefix : var.project_name}st${local.unique_suffix}",0,24))
  resource_group_name  = azurerm_resource_group.main.name
  location            = var.location
  
  account_tier       = var.storage_account_tier
  replication_type   = var.storage_account_replication_type
  
  private_endpoint_enabled   = false
  private_endpoint_subnet_id = ""
  
  # CDN is always enabled - no configuration needed
  
  tags = local.common_tags
  
  depends_on = [module.network]
}

# API Management (optional)
module "apim" {
  source = "./modules/apim"
  
  enable_apim         = var.enable_api_management
  apim_name          = "${local.resource_prefix}-apim"
  resource_group_name = azurerm_resource_group.main.name
  location           = var.location
  
  sku_name         = var.apim_sku_name
  publisher_name   = var.apim_publisher_name
  publisher_email  = var.apim_publisher_email
  
  backend_service_url = var.backend_internal_url
  
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
  
  aks_cluster_id = module.aks.cluster_id
  
  tags = local.common_tags
  
  depends_on = [module.aks]
} 