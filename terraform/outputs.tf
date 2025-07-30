# Resource Group
output "resource_group_name" {
  description = "Name of the main resource group"
  value       = azurerm_resource_group.main.name
}

# AKS outputs
output "aks_cluster_name" {
  description = "Name of the AKS cluster"
  value       = module.aks.cluster_name
}

output "aks_resource_group" {
  description = "Resource group of the AKS cluster"
  value       = azurerm_resource_group.main.name
}

output "kubectl_config_command" {
  description = "Command to configure kubectl"
  value       = "az aks get-credentials --resource-group ${azurerm_resource_group.main.name} --name ${module.aks.cluster_name}"
}

# ACR outputs
output "acr_login_server" {
  description = "Login server of the Azure Container Registry"
  value       = module.acr.login_server
}

output "acr_name" {
  description = "Name of the Azure Container Registry"
  value       = module.acr.name
}

# Database outputs
output "postgres_fqdn" {
  description = "FQDN of the PostgreSQL server"
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "postgres_database_name" {
  description = "Name of the PostgreSQL database"
  value       = azurerm_postgresql_flexible_server_database.main.name
}

# Storage outputs
output "storage_account_name" {
  description = "Name of the storage account"
  value       = module.storage.storage_account_name
}

output "storage_account_primary_access_key" {
  description = "Primary access key for the storage account"
  value       = module.storage.primary_access_key
  sensitive   = true
}

# CDN Outputs (ALWAYS ENABLED)
output "cdn_enabled" {
  description = "Whether CDN is enabled"
  value       = true
}

output "cdn_endpoint_fqdn" {
  description = "FQDN of the Azure CDN endpoint"
  value       = module.storage.cdn_endpoint_fqdn
}

output "cdn_endpoint_url" {
  description = "Full CDN URL"
  value       = module.storage.cdn_endpoint_url
}

# Load balancer IP (will be available after K8s deployment)
output "application_url_info" {
  description = "Information about accessing the application"
  value = "Application will be available via LoadBalancer IP after K8s deployment. Run: kubectl get service -n hotcalls-${var.environment}"
} 