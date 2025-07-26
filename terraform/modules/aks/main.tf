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

  # Default node pool
  default_node_pool {
    name                = "default"
    node_count          = var.node_count
    vm_size            = var.node_size
    vnet_subnet_id     = var.vnet_subnet_id
    
    # Enable auto-scaling
    enable_auto_scaling = true
    min_count          = var.min_node_count
    max_count          = var.max_node_count
    
    # Node configuration
    os_disk_size_gb    = 50
    os_disk_type       = "Managed"
    
    # Upgrade settings
    upgrade_settings {
      max_surge = "10%"
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

  # Add-ons
  oms_agent {
    log_analytics_workspace_id = var.log_analytics_workspace_id
  }

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

# Additional node pool for workloads (optional)
resource "azurerm_kubernetes_cluster_node_pool" "workload" {
  count                 = var.enable_workload_node_pool ? 1 : 0
  name                  = "workload"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.main.id
  vm_size              = var.workload_node_size
  node_count           = var.workload_node_count
  vnet_subnet_id       = var.vnet_subnet_id
  
  # Enable auto-scaling
  enable_auto_scaling = true
  min_count          = 1
  max_count          = var.workload_max_node_count
  
  # Node configuration
  os_disk_size_gb = 50
  os_disk_type    = "Managed"
  
  # Node labels and taints for workload separation
  node_labels = {
    "nodepool-type" = "workload"
    "environment"   = var.environment
  }
  
  node_taints = [
    "workload=true:NoSchedule"
  ]
  
  tags = var.tags
} 