# ADR 0006: Azure Container Apps for the self-hosted Agent Server templates

**Status:** accepted

**Context.** The self-hosted Agent Server needs Postgres, Redis, secrets and always-on workers. LangChain
recommends Kubernetes for production.

**Decision.** Templates target Container Apps with Postgres Flexible Server, Azure Cache for Redis, Key Vault
references through a managed identity, `min_replicas >= 1` and an optional private network. Terraform and
Bicep stay equivalent and are tested statically; deployment is gated off.

**Consequences.** Smaller footprint than AKS for a portfolio; a client already on AKS should use the Helm chart.
