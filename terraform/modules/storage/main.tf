# Azure Storage Account for application files
resource "azurerm_storage_account" "main" {
  name                     = var.storage_account_name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = var.account_tier
  account_replication_type = var.replication_type
  
  # Security settings
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  
  # Network access rules
  public_network_access_enabled = var.public_access_enabled
  
  # Identity for Key Vault integration
  identity {
    type = "SystemAssigned"
  }
  
  tags = var.tags
}

# Container for static files
resource "azurerm_storage_container" "static" {
  name                  = "static"
  storage_account_name  = azurerm_storage_account.main.name
  # Private access (public blobs not permitted)
  container_access_type = "private"
}

# Container for media files
resource "azurerm_storage_container" "media" {
  name                  = "media"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# Container for backups
resource "azurerm_storage_container" "backups" {
  name                  = "backups"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# Azure CDN Profile for fast global delivery (ALWAYS ON)
resource "azurerm_cdn_profile" "main" {
  name                = "${var.storage_account_name}-cdn"
  location            = "Global"
  resource_group_name = var.resource_group_name
  sku                 = "Standard_Microsoft"
  tags                = var.tags
}

# CDN Endpoint pointing to blob storage (ALWAYS ON)
resource "azurerm_cdn_endpoint" "storage" {
  name                = "${var.storage_account_name}-endpoint"
  profile_name        = azurerm_cdn_profile.main.name
  location            = azurerm_cdn_profile.main.location
  resource_group_name = var.resource_group_name

  origin {
    name      = "storage"
    host_name = trimsuffix(replace(azurerm_storage_account.main.primary_blob_endpoint, "https://", ""), "/")
  }
  
  is_http_allowed  = false
  is_https_allowed = true
  
  tags = var.tags
}

# Private endpoint for storage account
resource "azurerm_private_endpoint" "storage" {
  count               = var.private_endpoint_enabled ? 1 : 0
  name                = "${var.storage_account_name}-pe"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "${var.storage_account_name}-psc"
    private_connection_resource_id = azurerm_storage_account.main.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  tags = var.tags
} 