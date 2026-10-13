data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.suffix}-001"
  location = var.location
  tags     = local.tags
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "log-${local.suffix}"
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 1
  tags                = local.tags
}

resource "azurerm_user_assigned_identity" "app" {
  name                = "id-${local.suffix}-agentserver"
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

# ---------------------------------------------------------------- registry

resource "azurerm_container_registry" "this" {
  #checkov:skip=CKV_AZURE_139:public access is disabled when private_networking = true (prod); dev pulls over the public endpoint
  #checkov:skip=CKV_AZURE_163:image scanning is Defender for Containers, enabled at subscription level, not in this stack
  #checkov:skip=CKV_AZURE_164:content trust is not used: images are built by CI from this repo and pulled by digest
  #checkov:skip=CKV_AZURE_165:single-region workload; geo-replication is a Premium cost decision documented in docs/deployment.md
  #checkov:skip=CKV_AZURE_166:quarantine flow needs a scanner pipeline that this portfolio stack does not include
  #checkov:skip=CKV_AZURE_167:retention policy for untagged manifests is Premium-only; dev uses Basic
  #checkov:skip=CKV_AZURE_233:zone redundancy is Premium-only; dev uses Basic
  #checkov:skip=CKV_AZURE_237:dedicated data endpoints are Premium-only; dev uses Basic

  name                          = "cr${local.compact}"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.this.name
  sku                           = var.private_networking ? "Premium" : "Basic"
  admin_enabled                 = false
  public_network_access_enabled = !var.private_networking
  tags                          = local.tags
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.this.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# ---------------------------------------------------------------- Key Vault

resource "azurerm_key_vault" "this" {
  #checkov:skip=CKV_AZURE_189:public access is disabled when private_networking = true (prod); dev needs it for the operator to write the LangSmith key
  #checkov:skip=CKV_AZURE_109:network_acls default_action is Deny when private_networking = true (prod)
  #checkov:skip=CKV2_AZURE_32:the private endpoint exists when private_networking = true (network.tf)

  name                          = "kv-${substr(local.compact, 0, 21)}"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.this.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 90
  public_network_access_enabled = !var.private_networking

  network_acls {
    bypass         = "AzureServices"
    default_action = var.private_networking ? "Deny" : "Allow"
  }

  tags = local.tags
}

resource "azurerm_role_assignment" "kv_secrets_user" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "kv_deployer" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# ---------------------------------------------------------------- Postgres (checkpoints, threads, runs)

resource "random_password" "pg" {
  length  = 32
  special = false
}

resource "azurerm_postgresql_flexible_server" "this" {
  #checkov:skip=CKV_AZURE_136:geo-redundant backups are on in prod (environment == prod); off in dev to save cost
  #checkov:skip=CKV2_AZURE_57:private access uses VNet injection (delegated subnet + private DNS zone), not a private endpoint; public access is always off

  name                          = "psql-${local.suffix}"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.this.name
  version                       = "16"
  sku_name                      = var.postgres_sku
  storage_mb                    = var.postgres_storage_mb
  backup_retention_days         = var.environment == "prod" ? 35 : 7
  geo_redundant_backup_enabled  = var.environment == "prod"
  public_network_access_enabled = false
  delegated_subnet_id           = var.private_networking ? azurerm_subnet.postgres[0].id : null
  private_dns_zone_id           = var.private_networking ? azurerm_private_dns_zone.postgres[0].id : null
  administrator_login           = "agentserver"
  administrator_password        = random_password.pg.result
  zone                          = "1"

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = true
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }

  tags = local.tags

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}

resource "azurerm_postgresql_flexible_server_configuration" "require_tls" {
  name      = "require_secure_transport"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_connections" {
  name      = "log_connections"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_database" "agent" {
  name      = "agentserver"
  server_id = azurerm_postgresql_flexible_server.this.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# ---------------------------------------------------------------- Redis (run queue, streaming pub/sub)

resource "azurerm_redis_cache" "this" {
  #checkov:skip=CKV_AZURE_89:public access is disabled when private_networking = true (prod)
  #checkov:skip=CKV_AZURE_230:replication needs Standard/Premium; prod uses Premium, dev uses Basic

  name                          = "redis-${local.suffix}"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.this.name
  capacity                      = 0
  family                        = var.redis_sku == "Premium" ? "P" : "C"
  sku_name                      = var.redis_sku
  non_ssl_port_enabled          = false
  minimum_tls_version           = "1.2"
  public_network_access_enabled = !var.private_networking
  tags                          = local.tags

  redis_configuration {
    authentication_enabled = true
  }
}

resource "azurerm_key_vault_secret" "database_uri" {
  name            = local.kv_secret_names.database_uri
  key_vault_id    = azurerm_key_vault.this.id
  content_type    = "postgres connection string"
  expiration_date = "2099-01-01T00:00:00Z"
  value           = "postgres://agentserver:${random_password.pg.result}@${azurerm_postgresql_flexible_server.this.fqdn}:5432/agentserver?sslmode=require"
  depends_on      = [azurerm_role_assignment.kv_deployer]
}

resource "azurerm_key_vault_secret" "redis_uri" {
  name            = local.kv_secret_names.redis_uri
  key_vault_id    = azurerm_key_vault.this.id
  content_type    = "redis connection string"
  expiration_date = "2099-01-01T00:00:00Z"
  value           = "rediss://:${azurerm_redis_cache.this.primary_access_key}@${azurerm_redis_cache.this.hostname}:${azurerm_redis_cache.this.ssl_port}/0"
  depends_on      = [azurerm_role_assignment.kv_deployer]
}

# ---------------------------------------------------------------- Container Apps (Agent Server)

resource "azurerm_container_app_environment" "this" {
  name                           = "cae-${local.suffix}"
  location                       = var.location
  resource_group_name            = azurerm_resource_group.this.name
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.this.id
  infrastructure_subnet_id       = var.private_networking ? azurerm_subnet.apps[0].id : null
  internal_load_balancer_enabled = var.private_networking ? true : null
  tags                           = local.tags
}

resource "azurerm_container_app" "agent_server" {
  name                         = "ca-${local.suffix}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = azurerm_resource_group.this.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  dynamic "secret" {
    for_each = local.kv_secret_names
    content {
      name                = secret.value
      key_vault_secret_id = "${azurerm_key_vault.this.vault_uri}secrets/${secret.value}"
      identity            = azurerm_user_assigned_identity.app.id
    }
  }

  ingress {
    external_enabled = !var.private_networking
    target_port      = 8000
    transport        = "http"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = "agent-server"
      image  = var.image
      cpu    = 1
      memory = "2Gi"

      env {
        name        = "DATABASE_URI"
        secret_name = local.kv_secret_names.database_uri
      }
      env {
        name        = "REDIS_URI"
        secret_name = local.kv_secret_names.redis_uri
      }
      env {
        name        = "LANGSMITH_API_KEY"
        secret_name = local.kv_secret_names.langsmith_api_key
      }
      env {
        name  = "LANGSMITH_ENDPOINT"
        value = var.langsmith_endpoint
      }
      env {
        name  = "LANGSMITH_TRACING"
        value = "true"
      }
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.app.client_id
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/ok"
      }
      readiness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/ok"
      }
    }
  }

  depends_on = [azurerm_role_assignment.kv_secrets_user, azurerm_role_assignment.acr_pull, azurerm_key_vault_secret.database_uri, azurerm_key_vault_secret.redis_uri]
}
