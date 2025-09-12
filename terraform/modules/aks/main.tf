# AKS Managed Identity
resource "azurerm_user_assigned_identity" "aks" {
  name                = "${var.name}-identity"
  location           = var.location
  resource_group_name = var.resource_group_name
  tags               = var.tags
}

# AKS Cluster
resource "azurerm_kubernetes_cluster" "main" {
  name                = var.name
  location           = var.location
  resource_group_name = var.resource_group_name
  dns_prefix          = "${var.name}-k8s"
  kubernetes_version  = var.kubernetes_version
  tags               = var.tags

  # Default node pool (system only)
  default_node_pool {
    name                         = "system"
    node_count                   = 2
    vm_size                     = "Standard_D2as_v5"
    vnet_subnet_id              = var.vnet_subnet_id
    only_critical_addons_enabled = true
    
    # Enable auto-scaling
    enable_auto_scaling = true
    min_count          = 1
    max_count          = 2
    
    # Node configuration
    os_disk_size_gb    = 50
    os_disk_type       = "Managed"
    
    # Upgrade settings
    upgrade_settings {
      max_surge = "10%"
    }
    
    node_labels = {
      "workload" = "system"
    }
    
    tags = var.tags
  }

  # Use managed identity
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.aks.id]
  }

  # Network configuration
  network_profile {
    network_plugin    = "azure"
    network_policy    = "azure"
    dns_service_ip    = "10.2.0.10"
    service_cidr      = "10.2.0.0/24"
    load_balancer_sku = "standard"
  }

  # Enable Azure integrations
  azure_policy_enabled             = true
  http_application_routing_enabled  = false
  role_based_access_control_enabled = true

  # Azure Active Directory integration
  azure_active_directory_role_based_access_control {
    managed            = true
    azure_rbac_enabled = true
  }

# Add-ons (OMS agent removed – will be added later when workspace is available)

  key_vault_secrets_provider {
    secret_rotation_enabled = true
  }

  # Maintenance window
  maintenance_window {
    allowed {
      day   = "Sunday"
      hours = [1, 2]
    }
  }

  lifecycle {
    ignore_changes = [
      default_node_pool[0].node_count
    ]
  }
}

# Assign ACR pull role to AKS managed identity
resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.aks.principal_id
}

# Web node pool (Django backend + frontend)
resource "azurerm_kubernetes_cluster_node_pool" "web" {
  name                  = "web"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size              = "Standard_D4as_v5"
  node_count           = 1
  vnet_subnet_id       = var.vnet_subnet_id
  
  # Enable auto-scaling
  enable_auto_scaling = true
  min_count          = 1
  max_count          = 3
  
  # Node configuration
  os_disk_size_gb = 50
  os_disk_type    = "Managed"
  
  node_labels = {
    "workload" = "web"
  }
  
  tags = var.tags
}

# Workers node pool (Celery workers - compute optimized)
resource "azurerm_kubernetes_cluster_node_pool" "workers" {
  name                  = "workers"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size              = "Standard_F4s_v2"
  node_count           = 1
  vnet_subnet_id       = var.vnet_subnet_id
  
  # Enable auto-scaling
  enable_auto_scaling = true
  min_count          = 1
  max_count          = 2
  
  # Node configuration
  os_disk_size_gb = 50
  os_disk_type    = "Managed"
  
  node_labels = {
    "workload" = "workers"
  }
  
  tags = var.tags
}

# Scheduler node pool (Celery Beat + Redis)
resource "azurerm_kubernetes_cluster_node_pool" "scheduler" {
  name                  = "scheduler"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size              = "Standard_D2as_v5"
  node_count           = 1
  vnet_subnet_id       = var.vnet_subnet_id
  
  # No auto-scaling for scheduler (fixed single node)
  enable_auto_scaling = false
  
  # Node configuration
  os_disk_size_gb = 50
  os_disk_type    = "Managed"
  
  node_labels = {
    "workload" = "scheduler"
  }
  
  tags = var.tags
}

# Realtime node pool (LiveKit agent - high performance)
resource "azurerm_kubernetes_cluster_node_pool" "realtime" {
  name                  = "realtime"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size              = "Standard_F16s_v2"
  node_count           = 1
  vnet_subnet_id       = var.vnet_subnet_id
  
  # No auto-scaling for realtime (fixed single node for now)
  enable_auto_scaling = false
  
  # Node configuration
  os_disk_size_gb       = 50
  os_disk_type         = "Managed"
  enable_node_public_ip = false
  
  node_labels = {
    "workload" = "realtime"
  }
  
  tags = var.tags
} 