locals {
  region_short = { eastus2 = "eus2", eastus = "eus", westeurope = "weu", northeurope = "neu", uksouth = "uks" }
  suffix       = "${var.workload}-${var.environment}-${lookup(local.region_short, var.location, var.location)}"
  compact      = replace(local.suffix, "-", "")
  tags = merge({
    workload    = var.workload
    environment = var.environment
    managed_by  = "terraform"
    repo        = "Jagadish-langchain-langgraph-langsmith"
  }, var.tags)

  # Secrets the Agent Server reads, all stored in Key Vault and referenced by the container app
  # through its managed identity. The LangSmith key is written by an operator, never by Terraform.
  kv_secret_names = {
    database_uri      = "database-uri"
    redis_uri         = "redis-uri"
    langsmith_api_key = "langsmith-api-key"
  }
}
