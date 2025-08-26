#!/bin/bash

echo "Importing remaining resources..."

# Network Security Groups
terraform import module.network.azurerm_network_security_group.aks /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Network/networkSecurityGroups/hotcalls-staging-ne-aks-nsg || true
terraform import module.network.azurerm_network_security_group.app_gateway /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Network/networkSecurityGroups/hotcalls-staging-ne-appgw-nsg || true
terraform import module.network.azurerm_network_security_group.private_endpoints /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Network/networkSecurityGroups/hotcalls-staging-ne-pe-nsg || true

# Public IP
terraform import module.network.azurerm_public_ip.ingress_static /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Network/publicIPAddresses/hotcalls-staging-ne-ingress-static-ip || true

# User Assigned Identity
terraform import module.aks.azurerm_user_assigned_identity.aks /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.ManagedIdentity/userAssignedIdentities/hotcalls-staging-ne-aks-identity || true

# Application Insights
terraform import module.monitoring.azurerm_application_insights.main /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Insights/components/hotcalls-staging-ne-appinsights || true

# Action Group
terraform import module.monitoring.azurerm_monitor_action_group.main /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Insights/actionGroups/hotcalls-action-group || true

# Metric Alerts
terraform import 'module.monitoring.azurerm_monitor_metric_alert.cpu_usage[0]' /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Insights/metricAlerts/hotcalls-high-cpu || true
terraform import 'module.monitoring.azurerm_monitor_metric_alert.memory_usage[0]' /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Insights/metricAlerts/hotcalls-high-memory || true

# PostgreSQL Database
terraform import azurerm_postgresql_flexible_server_database.main /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.DBforPostgreSQL/flexibleServers/hotcalls-staging-ne-postgres/databases/hotcalls_db || true

# PostgreSQL Firewall Rule
terraform import azurerm_postgresql_flexible_server_firewall_rule.azure_services /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.DBforPostgreSQL/flexibleServers/hotcalls-staging-ne-postgres/firewallRules/AllowAzureServices || true

# Storage Containers
terraform import module.storage.azurerm_storage_container.media /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Storage/storageAccounts/stagingnewstagingnest5fz/blobServices/default/containers/media || true
terraform import module.storage.azurerm_storage_container.static /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Storage/storageAccounts/stagingnewstagingnest5fz/blobServices/default/containers/static || true
terraform import module.storage.azurerm_storage_container.backups /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Storage/storageAccounts/stagingnewstagingnest5fz/blobServices/default/containers/backups || true

echo "All resources imported!"
