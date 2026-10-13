# Private networking option: a VNet with a Container Apps infrastructure subnet, a delegated subnet
# for Postgres Flexible Server (VNet injection) and a subnet for private endpoints (Redis, Key Vault).

resource "azurerm_virtual_network" "this" {
  count               = var.private_networking ? 1 : 0
  name                = "vnet-${local.suffix}"
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  address_space       = [var.vnet_address_space]
  tags                = local.tags
}

resource "azurerm_subnet" "apps" {
  count                = var.private_networking ? 1 : 0
  name                 = "snet-apps"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this[0].name
  address_prefixes     = [cidrsubnet(var.vnet_address_space, 7, 0)]
}

resource "azurerm_subnet" "postgres" {
  count                = var.private_networking ? 1 : 0
  name                 = "snet-postgres"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this[0].name
  address_prefixes     = [cidrsubnet(var.vnet_address_space, 8, 4)]

  delegation {
    name = "postgres"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "endpoints" {
  count                = var.private_networking ? 1 : 0
  name                 = "snet-endpoints"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this[0].name
  address_prefixes     = [cidrsubnet(var.vnet_address_space, 8, 5)]
}

resource "azurerm_private_dns_zone" "postgres" {
  count               = var.private_networking ? 1 : 0
  name                = "${local.compact}.private.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  count                 = var.private_networking ? 1 : 0
  name                  = "postgres"
  resource_group_name   = azurerm_resource_group.this.name
  private_dns_zone_name = azurerm_private_dns_zone.postgres[0].name
  virtual_network_id    = azurerm_virtual_network.this[0].id
}

locals {
  private_endpoints = var.private_networking ? {
    redis = { id = azurerm_redis_cache.this.id, subresource = "redisCache", zone = "privatelink.redis.cache.windows.net" }
    vault = { id = azurerm_key_vault.this.id, subresource = "vault", zone = "privatelink.vaultcore.azure.net" }
  } : {}
}

resource "azurerm_private_dns_zone" "pe" {
  for_each            = local.private_endpoints
  name                = each.value.zone
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "pe" {
  for_each              = local.private_endpoints
  name                  = each.key
  resource_group_name   = azurerm_resource_group.this.name
  private_dns_zone_name = azurerm_private_dns_zone.pe[each.key].name
  virtual_network_id    = azurerm_virtual_network.this[0].id
}

resource "azurerm_private_endpoint" "this" {
  for_each            = local.private_endpoints
  name                = "pe-${each.key}-${local.suffix}"
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = azurerm_subnet.endpoints[0].id
  tags                = local.tags

  private_service_connection {
    name                           = each.key
    private_connection_resource_id = each.value.id
    subresource_names              = [each.value.subresource]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = each.key
    private_dns_zone_ids = [azurerm_private_dns_zone.pe[each.key].id]
  }
}

# One NSG per subnet; Azure's default rules allow VNet-internal traffic and deny inbound from the internet.
resource "azurerm_network_security_group" "this" {
  for_each            = var.private_networking ? toset(["apps", "postgres", "endpoints"]) : toset([])
  name                = "nsg-${each.key}-${local.suffix}"
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_subnet_network_security_group_association" "this" {
  for_each = var.private_networking ? {
    apps      = azurerm_subnet.apps[0].id
    postgres  = azurerm_subnet.postgres[0].id
    endpoints = azurerm_subnet.endpoints[0].id
  } : {}
  subnet_id                 = each.value
  network_security_group_id = azurerm_network_security_group.this[each.key].id
}
