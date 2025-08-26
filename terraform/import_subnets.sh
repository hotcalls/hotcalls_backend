#!/bin/bash
echo "Importing subnets..."

terraform import module.network.azurerm_subnet.aks /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Network/virtualNetworks/hotcalls-staging-ne-vnet/subnets/hotcalls-staging-ne-aks-subnet || true

terraform import module.network.azurerm_subnet.app_gateway /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Network/virtualNetworks/hotcalls-staging-ne-vnet/subnets/hotcalls-staging-ne-appgw-subnet || true

terraform import module.network.azurerm_subnet.private_endpoints /subscriptions/b9716013-6c1a-4a3c-919e-6e3be8231c22/resourceGroups/staging-new/providers/Microsoft.Network/virtualNetworks/hotcalls-staging-ne-vnet/subnets/hotcalls-staging-ne-pe-subnet || true

echo "Subnets imported!"
