# Offline plan tests: mocked providers, no Azure credentials, nothing created.
#   terraform init -backend=false && terraform test
mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id       = "00000000-0000-0000-0000-000000000001"
      subscription_id = "00000000-0000-0000-0000-000000000002"
      object_id       = "00000000-0000-0000-0000-000000000003"
    }
  }
}

mock_provider "random" {}

override_resource {
  target          = azurerm_key_vault.this
  override_during = plan
  values = {
    id        = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg/providers/Microsoft.KeyVault/vaults/kv-lcdesk"
    vault_uri = "https://kv-lcdesk.vault.azure.net/"
  }
}

override_resource {
  target          = azurerm_user_assigned_identity.app
  override_during = plan
  values = {
    id           = "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-lcdesk"
    principal_id = "00000000-0000-0000-0000-000000000004"
    client_id    = "00000000-0000-0000-0000-000000000005"
  }
}

run "dev_defaults" {
  command = plan

  variables {
    environment = "dev"
  }

  assert {
    condition     = azurerm_resource_group.this.name == "rg-lcdesk-dev-eus2-001"
    error_message = "resource group follows the CAF naming pattern"
  }

  assert {
    condition     = length(azurerm_virtual_network.this) == 0 && length(azurerm_private_endpoint.this) == 0
    error_message = "no VNet or private endpoints unless private networking is on"
  }

  assert {
    condition     = azurerm_container_app.agent_server.ingress[0].external_enabled
    error_message = "dev exposes the Agent Server ingress"
  }

  assert {
    condition     = azurerm_container_app.agent_server.template[0].min_replicas >= 1
    error_message = "no scale-to-zero: the Agent Server runs background workers"
  }

  assert {
    condition     = !azurerm_container_registry.this.admin_enabled
    error_message = "registry pulls use the managed identity, not admin credentials"
  }

  assert {
    condition     = azurerm_key_vault.this.rbac_authorization_enabled && azurerm_key_vault.this.purge_protection_enabled
    error_message = "Key Vault uses RBAC and purge protection"
  }

  assert {
    condition     = !azurerm_redis_cache.this.non_ssl_port_enabled && azurerm_redis_cache.this.minimum_tls_version == "1.2"
    error_message = "Redis only over TLS 1.2+"
  }

  assert {
    condition     = !azurerm_postgresql_flexible_server.this.public_network_access_enabled
    error_message = "Postgres is never publicly reachable"
  }

  assert {
    condition     = azurerm_postgresql_flexible_server_configuration.require_tls.value == "on"
    error_message = "Postgres requires TLS"
  }

  assert {
    condition     = alltrue([for s in azurerm_container_app.agent_server.secret : startswith(s.key_vault_secret_id, "https://kv-lcdesk.vault.azure.net/secrets/")])
    error_message = "every container secret is a Key Vault reference"
  }

  assert {
    condition     = contains([for s in azurerm_container_app.agent_server.secret : s.name], "langsmith-api-key")
    error_message = "the LangSmith key comes from Key Vault"
  }

  assert {
    condition     = azurerm_role_assignment.kv_secrets_user.role_definition_name == "Key Vault Secrets User" && azurerm_role_assignment.acr_pull.role_definition_name == "AcrPull"
    error_message = "the app identity can read secrets and pull images, nothing more"
  }
}

run "prod_private" {
  command = plan

  variables {
    environment        = "prod"
    private_networking = true
    min_replicas       = 2
    redis_sku          = "Premium"
    postgres_sku       = "GP_Standard_D2ds_v5"
  }

  assert {
    condition     = length(azurerm_virtual_network.this) == 1 && length(azurerm_private_endpoint.this) == 2
    error_message = "private networking creates a VNet and private endpoints for Redis and Key Vault"
  }

  assert {
    condition     = !azurerm_container_app.agent_server.ingress[0].external_enabled && azurerm_container_app_environment.this.internal_load_balancer_enabled
    error_message = "prod ingress is internal only"
  }

  assert {
    condition     = !azurerm_redis_cache.this.public_network_access_enabled && !azurerm_key_vault.this.public_network_access_enabled && !azurerm_container_registry.this.public_network_access_enabled
    error_message = "no public network access to Redis, Key Vault or the registry"
  }

  assert {
    condition     = azurerm_postgresql_flexible_server.this.geo_redundant_backup_enabled && azurerm_postgresql_flexible_server.this.backup_retention_days == 35
    error_message = "prod Postgres keeps geo-redundant backups for 35 days"
  }
}

run "rejects_scale_to_zero" {
  command = plan

  variables {
    environment  = "dev"
    min_replicas = 0
  }

  expect_failures = [var.min_replicas]
}
