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