output "AZURE_RESOURCE_GROUP" {
  value = azurerm_resource_group.this.name
}

output "container_app_name" {
  value = azurerm_container_app.agent_server.name
}

output "agent_server_fqdn" {
  value = azurerm_container_app.agent_server.ingress[0].fqdn
}

output "registry_login_server" {
  value = azurerm_container_registry.this.login_server
}

output "key_vault_name" {
  description = "Write the LangSmith key here as secret langsmith-api-key before the first revision starts"
  value       = azurerm_key_vault.this.name
}
