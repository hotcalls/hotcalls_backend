# Private DNS Zone for PostgreSQL
resource "azurerm_private_dns_zone" "postgres" {
  name                = "${var.name}.private.postgres.database.azure.com"
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

# Private DNS Zone Virtual Network Link
resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "${var.name}-dns-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = var.virtual_network_id
  registration_enabled  = false
  tags                  = var.tags
}

# PostgreSQL Flexible Server
resource "azurerm_postgresql_flexible_server" "main" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location           = var.location
  
  # Server configuration
  version                = var.postgres_version
  administrator_login    = var.admin_username
  administrator_password = var.admin_password
  
  # SKU configuration
  sku_name = var.sku_name
  
  # Storage configuration
  storage_mb = var.storage_mb
  
  # Backup configuration
  backup_retention_days        = var.backup_retention_days
  geo_redundant_backup_enabled = var.geo_redundant_backup_enabled
  
  # Network configuration - private access
  delegated_subnet_id = var.delegated_subnet_id
  private_dns_zone_id = azurerm_private_dns_zone.postgres.id
  
  # High availability (optional)
  dynamic "high_availability" {
    for_each = var.high_availability_enabled ? [1] : []
    content {
      mode                      = "ZoneRedundant"
      standby_availability_zone = var.standby_availability_zone
    }
  }
  
  # Maintenance window
  maintenance_window {
    day_of_week  = var.maintenance_window.day_of_week
    start_hour   = var.maintenance_window.start_hour
    start_minute = var.maintenance_window.start_minute
  }
  
  # Authentication configuration
  authentication {
    active_directory_auth_enabled = var.azure_ad_auth_enabled
    password_auth_enabled         = true
    tenant_id                     = var.tenant_id
  }
  
  tags = var.tags
  
  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}

# PostgreSQL Database
resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = var.database_name
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "utf8"
}

# PostgreSQL Configuration (optional settings)
resource "azurerm_postgresql_flexible_server_configuration" "shared_preload_libraries" {
  count     = var.enable_extensions ? 1 : 0
  name      = "shared_preload_libraries"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "pg_stat_statements,pg_cron"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_statement" {
  name      = "log_statement"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "all"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_min_duration_statement" {
  name      = "log_min_duration_statement"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "1000" # Log queries taking longer than 1 second
}

# Firewall rules (if public access is needed for specific IPs)
resource "azurerm_postgresql_flexible_server_firewall_rule" "allowed_ips" {
  count            = length(var.allowed_ip_ranges)
  name             = "AllowedIP-${count.index}"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = split("/", var.allowed_ip_ranges[count.index])[0]
  end_ip_address   = split("/", var.allowed_ip_ranges[count.index])[0]
}

# Diagnostic settings for monitoring
resource "azurerm_monitor_diagnostic_setting" "postgres" {
  count                      = var.log_analytics_workspace_id != null ? 1 : 0
  name                       = "${var.name}-diagnostics"
  target_resource_id         = azurerm_postgresql_flexible_server.main.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  # Enable PostgreSQL logs
  enabled_log {
    category = "PostgreSQLLogs"
  }

  # Enable all available metrics
  metric {
    category = "AllMetrics"
    enabled  = true
  }
} 