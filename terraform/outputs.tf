# Resource Group
output "resource_group_name" {
  description = "Name of the main resource group"
  value       = azurerm_resource_group.main.name
}

output "resource_group_id" {
  description = "ID of the main resource group"
  value       = azurerm_resource_group.main.id
}

# Network outputs
output "vnet_id" {
  description = "ID of the virtual network"
  value       = module.network.vnet_id
}

output "vnet_name" {
  description = "Name of the virtual network"
  value       = module.network.vnet_name
}

output "aks_subnet_id" {
  description = "ID of the AKS subnet"
  value       = module.network.aks_subnet_id
}

# AKS outputs
output "aks_cluster_name" {
  description = "Name of the AKS cluster"
  value       = module.aks.cluster_name
}

output "aks_cluster_id" {
  description = "ID of the AKS cluster"
  value       = module.aks.cluster_id
}

output "aks_fqdn" {
  description = "FQDN of the AKS cluster"
  value       = module.aks.cluster_fqdn
}

output "aks_principal_id" {
  description = "Principal ID of the AKS managed identity"
  value       = module.aks.principal_id
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

output "acr_admin_username" {
  description = "Admin username for the Azure Container Registry"
  value       = module.acr.admin_username
  sensitive   = true
}

output "acr_admin_password" {
  description = "Admin password for the Azure Container Registry"
  value       = module.acr.admin_password
  sensitive   = true
}

# Database outputs
output "postgres_fqdn" {
  description = "FQDN of the PostgreSQL server"
  value       = module.postgres.fqdn
}

output "postgres_admin_username" {
  description = "PostgreSQL administrator username"
  value       = var.postgres_admin_username
  sensitive   = true
}

# Temporary output to get the actual password for debugging
output "postgres_admin_password" {
  description = "PostgreSQL administrator password (temporary for debugging)"
  value       = local.postgres_password
  sensitive   = true
}

output "postgres_database_name" {
  description = "Name of the PostgreSQL database"
  value       = module.postgres.database_name
}

# Key Vault outputs
output "key_vault_name" {
  description = "Name of the Key Vault"
  value       = module.keyvault.name
}

output "key_vault_id" {
  description = "ID of the Key Vault"
  value       = module.keyvault.id
}

output "key_vault_uri" {
  description = "URI of the Key Vault"
  value       = module.keyvault.vault_uri
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

output "storage_static_container_name" {
  description = "Name of the static files container"
  value       = module.storage.static_container_name
}

output "storage_media_container_name" {
  description = "Name of the media files container"
  value       = module.storage.media_container_name
}

# API Management outputs
output "apim_gateway_url" {
  description = "Gateway URL for API Management"
  value       = module.apim.apim_gateway_url
}

output "apim_developer_portal_url" {
  description = "Developer portal URL for API Management"
  value       = module.apim.apim_gateway_url
}

output "apim_management_api_url" {
  description = "Management API URL for API Management"
  value       = module.apim.apim_management_api_url
}

# Monitoring outputs
output "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace"
  value       = module.monitoring.log_analytics_workspace_id
}

output "application_insights_connection_string" {
  description = "Connection string for Application Insights"
  value       = var.enable_application_insights ? module.monitoring.application_insights_connection_string : null
  sensitive   = true
}

output "application_insights_instrumentation_key" {
  description = "Instrumentation key for Application Insights"
  value       = var.enable_application_insights ? module.monitoring.application_insights_key : null
  sensitive   = true
}

# Environment variables for Django deployment
output "django_environment_variables" {
  description = "Environment variables needed for Django deployment"
  value = {
    # Django settings
    ENVIRONMENT                        = var.environment
    SECRET_KEY                        = "# Retrieved from Key Vault"
    ALLOWED_HOSTS                     = var.custom_domain != null ? "${module.apim.apim_gateway_url},${var.custom_domain}" : module.apim.apim_gateway_url
    
    # Database configuration
    DB_HOST                          = module.postgres.fqdn
    DB_NAME                          = module.postgres.database_name
    DB_USER                          = var.postgres_admin_username
    DB_PASSWORD                      = "# Retrieved from Key Vault"
    DB_SSLMODE                       = "require"
    
    # Azure Storage
    AZURE_ACCOUNT_NAME               = module.storage.storage_account_name
    AZURE_STORAGE_KEY                = "# Retrieved from Key Vault"
    AZURE_STATIC_CONTAINER           = module.storage.static_container_name
    AZURE_MEDIA_CONTAINER            = module.storage.media_container_name
    # CDN not yet implemented – leaving null
    AZURE_CUSTOM_DOMAIN              = null
    
    # Azure Key Vault
    AZURE_KEY_VAULT_URL              = module.keyvault.vault_uri
    
    # Application Insights
    AZURE_MONITOR_CONNECTION_STRING  = var.enable_application_insights ? "# Retrieved from Key Vault" : null
    
    # API configuration
    BASE_URL                         = var.enable_api_management ? "https://${module.apim.apim_gateway_url}" : "https://hotcalls-dev.local"
  }
  sensitive = true
}

# Kubernetes deployment outputs
output "kubernetes_namespace" {
  description = "Kubernetes namespace name"
  value       = module.kubernetes.namespace_name
}

output "kubernetes_backend_service" {
  description = "Backend service name"
  value       = module.kubernetes.backend_service_name
}

output "kubernetes_frontend_service" {
  description = "Frontend service name"
  value       = module.kubernetes.frontend_service_name
}

output "kubernetes_ingress" {
  description = "Ingress name"
  value       = module.kubernetes.ingress_name
}

# Deployment instructions (updated for Terraform-managed deployment)
output "deployment_instructions" {
  description = "Next steps for deployment"
  value = {
    "1_build_and_push_images" = "Build and push Docker images to ${module.acr.login_server}"
    "2_run_terraform_apply"   = "Run: terraform apply with .env variables"
    "3_access_application"    = "Application will be available through the ingress"
    "4_view_pods"            = "View pods: kubectl get pods -n ${module.kubernetes.namespace_name}"
  }
} 