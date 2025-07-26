output "id" {
  description = "ID of the Key Vault"
  value       = azurerm_key_vault.main.id
}

output "name" {
  description = "Name of the Key Vault"
  value       = azurerm_key_vault.main.name
}

output "vault_uri" {
  description = "URI of the Key Vault"
  value       = azurerm_key_vault.main.vault_uri
}

output "tenant_id" {
  description = "Tenant ID of the Key Vault"
  value       = azurerm_key_vault.main.tenant_id
}

output "private_endpoint_id" {
  description = "ID of the private endpoint (if enabled)"
  value       = var.enable_private_endpoint ? azurerm_private_endpoint.keyvault[0].id : null
}

output "private_dns_zone_id" {
  description = "ID of the private DNS zone (if private endpoint is enabled)"
  value       = var.enable_private_endpoint ? azurerm_private_dns_zone.keyvault[0].id : null
}

output "secret_ids" {
  description = "Map of secret names to their IDs"
  value       = { for k, v in azurerm_key_vault_secret.secrets : k => v.id }
} 