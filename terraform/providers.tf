# Configure the Microsoft Azure Provider
provider "azurerm" {
  features {
    # Enable soft delete for Key Vault
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
    
    # Resource group deletion policy
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
    
    # API Management policies
    api_management {
      purge_soft_delete_on_destroy = false
      recover_soft_deleted         = true
    }
  }
}

# Configure the Azure Active Directory Provider
provider "azuread" {
  # Configuration will be loaded from environment variables
}

# Configure Kubernetes provider (will be configured after AKS creation)
provider "kubernetes" {
  host                   = try(module.aks.cluster_endpoint, null)
  client_certificate     = try(base64decode(module.aks.client_certificate), null)
  client_key             = try(base64decode(module.aks.client_key), null)
  cluster_ca_certificate = try(base64decode(module.aks.cluster_ca_certificate), null)
}

# Configure Helm provider (will be configured after AKS creation)
provider "helm" {
  kubernetes {
    host                   = try(module.aks.cluster_endpoint, null)
    client_certificate     = try(base64decode(module.aks.client_certificate), null)
    client_key             = try(base64decode(module.aks.client_key), null)
    cluster_ca_certificate = try(base64decode(module.aks.cluster_ca_certificate), null)
  }
} 