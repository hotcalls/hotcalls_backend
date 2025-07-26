# Get current client configuration
data "azurerm_client_config" "current" {}

# Azure Key Vault
resource "azurerm_key_vault" "main" {
  name                        = var.name
  location                   = var.location
  resource_group_name        = var.resource_group_name
  enabled_for_disk_encryption = true
  tenant_id                  = var.tenant_id
  soft_delete_retention_days  = var.soft_delete_retention_days
  purge_protection_enabled   = var.purge_protection_enabled
  sku_name                   = var.sku_name
  tags                       = var.tags

  # Network access configuration
  public_network_access_enabled = var.public_network_access_enabled
  
  # Network ACLs
  network_acls {
    bypass         = "AzureServices"
    default_action = var.network_acls_default_action

    # Allow specific IP ranges
    ip_rules = var.allowed_ip_ranges

    # Allow specific virtual networks
    virtual_network_subnet_ids = var.allowed_subnet_ids
  }

  # RBAC authentication
  enable_rbac_authorization = var.enable_rbac_authorization
}

# Private endpoint for Key Vault
resource "azurerm_private_endpoint" "keyvault" {
  count               = var.enable_private_endpoint ? 1 : 0
  name                = "${var.name}-pe"
  location           = var.location
  resource_group_name = var.resource_group_name
  subnet_id          = var.private_endpoint_subnet_id
  tags               = var.tags

  private_service_connection {
    name                           = "${var.name}-psc"
    private_connection_resource_id = azurerm_key_vault.main.id
    subresource_names             = ["vault"]
    is_manual_connection          = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.keyvault[0].id]
  }
}

# Private DNS Zone for Key Vault
resource "azurerm_private_dns_zone" "keyvault" {
  count               = var.enable_private_endpoint ? 1 : 0
  name                = "privatelink.vaultcore.azure.net"
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

# Private DNS Zone Virtual Network Link
resource "azurerm_private_dns_zone_virtual_network_link" "keyvault" {
  count                 = var.enable_private_endpoint ? 1 : 0
  name                  = "${var.name}-dns-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.keyvault[0].name
  virtual_network_id    = var.virtual_network_id
  registration_enabled  = false
  tags                  = var.tags
}

# Access policy for current deployment principal
resource "azurerm_key_vault_access_policy" "current" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = var.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  secret_permissions = [
    "Get",
    "List",
    "Set",
    "Delete",
    "Recover",
    "Backup",
    "Restore",
    "Purge"
  ]

  key_permissions = [
    "Get",
    "List",
    "Create",
    "Delete",
    "Recover",
    "Backup",
    "Restore",
    "Purge"
  ]

  certificate_permissions = [
    "Get",
    "List",
    "Create",
    "Delete",
    "Recover",
    "Backup",
    "Restore",
    "Purge"
  ]
}

# Access policy for AKS managed identity
resource "azurerm_key_vault_access_policy" "aks" {
  count        = 1  # Always create; var.aks_principal_id will be populated
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = var.tenant_id
  object_id    = var.aks_principal_id

  secret_permissions = [
    "Get",
    "List"
  ]
}

# Additional access policies
resource "azurerm_key_vault_access_policy" "additional" {
  for_each     = var.additional_access_policies
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = var.tenant_id
  object_id    = each.value.object_id

  secret_permissions      = lookup(each.value, "secret_permissions", [])
  key_permissions        = lookup(each.value, "key_permissions", [])
  certificate_permissions = lookup(each.value, "certificate_permissions", [])
}

# Key Vault Secrets (simplified for dev)
# Note: In production, secrets should be added via CI/CD pipeline
# resource "azurerm_key_vault_secret" "secrets" {
#   for_each     = var.secrets
#   name         = each.key
#   value        = each.value
#   key_vault_id = azurerm_key_vault.main.id
#   tags         = var.tags
#
#   depends_on = [
#     azurerm_key_vault_access_policy.current
#   ]
# }

# Diagnostic settings for monitoring
resource "azurerm_monitor_diagnostic_setting" "keyvault" {
  count                      = var.log_analytics_workspace_id != null ? 1 : 0
  name                       = "${var.name}-diagnostics"
  target_resource_id         = azurerm_key_vault.main.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  # Enable Key Vault logs
  enabled_log {
    category = "AuditEvent"
  }

  enabled_log {
    category = "AzurePolicyEvaluationDetails"
  }

  # Enable all available metrics
  metric {
    category = "AllMetrics"
    enabled  = true
  }
} 