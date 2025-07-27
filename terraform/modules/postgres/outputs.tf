output "server_id" {
  description = "ID of the PostgreSQL server"
  value       = azurerm_postgresql_flexible_server.main.id
}

output "server_name" {
  description = "Name of the PostgreSQL server"
  value       = azurerm_postgresql_flexible_server.main.name
}

output "fqdn" {
  description = "FQDN of the PostgreSQL server"
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "database_name" {
  description = "Name of the database"
  value       = azurerm_postgresql_flexible_server_database.main.name
}

output "private_dns_zone_id" {
  description = "ID of the private DNS zone (if created)"
  value       = length(azurerm_private_dns_zone.postgres) > 0 ? azurerm_private_dns_zone.postgres[0].id : null
}

output "connection_string" {
  description = "PostgreSQL connection string"
  value       = "postgresql://${var.admin_username}:${var.admin_password}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.main.name}?sslmode=require"
  sensitive   = true
}

output "admin_username" {
  description = "Administrator username"
  value       = var.admin_username
  sensitive   = true
}

output "admin_password" {
  description = "Administrator password"
  value       = var.admin_password
  sensitive   = true
} 