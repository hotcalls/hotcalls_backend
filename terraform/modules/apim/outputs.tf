output "apim_id" {
  description = "ID of the API Management instance"
  value       = var.enable_apim ? azurerm_api_management.main[0].id : null
}

output "apim_gateway_url" {
  description = "Gateway URL of the API Management instance"
  value       = var.enable_apim ? azurerm_api_management.main[0].gateway_url : null
}

output "apim_management_api_url" {
  description = "Management API URL of the API Management instance"
  value       = var.enable_apim ? azurerm_api_management.main[0].management_api_url : null
} 