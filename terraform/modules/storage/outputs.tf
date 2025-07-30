output "storage_account_id" {
  description = "ID of the storage account"
  value       = azurerm_storage_account.main.id
}

output "storage_account_name" {
  description = "Name of the storage account"
  value       = azurerm_storage_account.main.name
}

output "primary_connection_string" {
  description = "Primary connection string"
  value       = azurerm_storage_account.main.primary_connection_string
  sensitive   = true
}

output "primary_access_key" {
  description = "Primary access key"
  value       = azurerm_storage_account.main.primary_access_key
  sensitive   = true
}

output "primary_blob_endpoint" {
  description = "Primary blob endpoint"
  value       = azurerm_storage_account.main.primary_blob_endpoint
}

output "static_container_name" {
  description = "Name of the static files container"
  value       = azurerm_storage_container.static.name
}

output "media_container_name" {
  description = "Name of the media files container"
  value       = azurerm_storage_container.media.name
}

output "backups_container_name" {
  description = "Name of the backups container"
  value       = azurerm_storage_container.backups.name
}

# CDN Outputs (ALWAYS AVAILABLE)
output "cdn_profile_id" {
  description = "ID of the CDN profile"
  value       = azurerm_cdn_profile.main.id
}

output "cdn_profile_name" {
  description = "Name of the CDN profile"
  value       = azurerm_cdn_profile.main.name
}

output "cdn_endpoint_id" {
  description = "ID of the CDN endpoint"
  value       = azurerm_cdn_endpoint.storage.id
}

output "cdn_endpoint_fqdn" {
  description = "FQDN of the CDN endpoint (Azure provided domain)"
  value       = azurerm_cdn_endpoint.storage.fqdn
}

output "cdn_endpoint_host_name" {
  description = "Host name of the CDN endpoint"
  value       = azurerm_cdn_endpoint.storage.fqdn
}

output "cdn_endpoint_url" {
  description = "Full CDN endpoint URL"
  value       = "https://${azurerm_cdn_endpoint.storage.fqdn}"
} 