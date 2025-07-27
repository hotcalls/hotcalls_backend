# Terraform backend configuration for Azure Blob Storage
# This stores the Terraform state file in Azure Storage for team collaboration
# and state locking to prevent concurrent modifications

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0"
    }
    postgresql = {
      source  = "cyrilgdn/postgresql"
      version = "~> 1.0"
    }
  }

  # Backend configuration commented out for local development
  # Uncomment and configure for production team environments
  # backend "azurerm" {
  #   resource_group_name  = "hotcalls-tfstate-rg"
  #   storage_account_name = "hotcallstfstate"
  #   container_name       = "tfstate"
  #   key                  = "hotcalls.tfstate"
  #   use_msi = false
  # }
} 