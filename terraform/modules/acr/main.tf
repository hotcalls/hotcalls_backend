# Azure Container Registry
resource "azurerm_container_registry" "main" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location           = var.location
  sku                = var.sku
  admin_enabled      = var.admin_enabled
  tags               = var.tags

  # Enable public network access (can be restricted later)
  public_network_access_enabled = var.public_network_access_enabled

  # Network rule set for additional security
  dynamic "network_rule_set" {
    for_each = var.network_rule_set_enabled ? [1] : []
    content {
      default_action = "Deny"

      # Allow specific IP ranges
      dynamic "ip_rule" {
        for_each = var.allowed_ip_ranges
        content {
          action   = "Allow"
          ip_range = ip_rule.value
        }
      }

      # Allow specific virtual networks
      dynamic "virtual_network" {
        for_each = var.allowed_subnet_ids
        content {
          action    = "Allow"
          subnet_id = virtual_network.value
        }
      }
    }
  }

  # Content trust and vulnerability scanning
  trust_policy {
    enabled = var.trust_policy_enabled
  }

  # Retention policy
  retention_policy {
    enabled = var.retention_policy_enabled
    days    = var.retention_days
  }

  # Quarantine policy
  quarantine_policy {
    enabled = var.quarantine_policy_enabled
  }

  # Zone redundancy for Premium SKU
  zone_redundancy_enabled = var.sku == "Premium" ? var.zone_redundancy_enabled : false

  # Export policy (for Premium SKU)
  export_policy_enabled = var.sku == "Premium" ? var.export_policy_enabled : null

  # Anonymous pull access (disabled by default for security)
  anonymous_pull_enabled = false

  # Data endpoint (for Premium SKU)
  data_endpoint_enabled = var.sku == "Premium" ? var.data_endpoint_enabled : false
}

# Diagnostic settings for monitoring
resource "azurerm_monitor_diagnostic_setting" "acr" {
  count                      = var.log_analytics_workspace_id != null ? 1 : 0
  name                       = "${var.name}-diagnostics"
  target_resource_id         = azurerm_container_registry.main.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  # Enable all available logs
  enabled_log {
    category = "ContainerRegistryRepositoryEvents"
  }

  enabled_log {
    category = "ContainerRegistryLoginEvents"
  }

  # Enable all available metrics
  metric {
    category = "AllMetrics"
    enabled  = true
  }
} 