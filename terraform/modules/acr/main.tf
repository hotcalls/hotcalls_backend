# Azure Container Registry
resource "azurerm_container_registry" "main" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku
  admin_enabled       = var.admin_enabled

  # Public network access
  public_network_access_enabled = var.public_network_access_enabled

  # Content trust (Premium only)
  trust_policy {
    enabled = var.sku == "Premium" ? var.trust_policy_enabled : false
  }

  # Retention policy (Premium only)  
  retention_policy {
    enabled = var.sku == "Premium" ? var.retention_policy_enabled : false
    days    = var.sku == "Premium" ? var.retention_days : 1
  }

  tags = var.tags
}

# Diagnostic settings (simplified for dev)
# resource "azurerm_monitor_diagnostic_setting" "acr" {
#   count              = var.log_analytics_workspace_id != "" ? 1 : 0
#   name               = "${var.name}-diagnostics"
#   target_resource_id = azurerm_container_registry.main.id
#   log_analytics_workspace_id = var.log_analytics_workspace_id
#
#   enabled_log {
#     category = "ContainerRegistryRepositoryEvents"
#   }
#
#   enabled_log {
#     category = "ContainerRegistryLoginEvents"
#   }
#
#   metric {
#     category = "AllMetrics"
#     enabled  = true
#   }
# } 