# API Management Service
resource "azurerm_api_management" "main" {
  count               = var.enable_apim ? 1 : 0
  name                = var.apim_name
  location            = var.location
  resource_group_name = var.resource_group_name
  publisher_name      = var.publisher_name
  publisher_email     = var.publisher_email
  sku_name            = var.sku_name

  # Basic identity
  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}

# API for HotCalls
resource "azurerm_api_management_api" "hotcalls" {
  count               = var.enable_apim ? 1 : 0
  name                = "hotcalls-api"
  resource_group_name = var.resource_group_name
  api_management_name = azurerm_api_management.main[0].name
  revision            = "1"
  display_name        = "HotCalls API"
  path                = "api"
  protocols           = ["https"]
  service_url         = var.backend_service_url

  description = "HotCalls Django REST API"

  import {
    content_format = "openapi+json-link"
    content_value  = "${var.backend_service_url}/api/schema/"
  }
} 