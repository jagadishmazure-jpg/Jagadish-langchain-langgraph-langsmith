# Deployment: Agent Server, managed versus self-hosted

Nothing in this repository has been deployed. The configuration is validated offline, the Agent Server
is started locally in CI, and the Azure templates are tested with mocked providers. The deploy workflow
is gated off.

## langgraph.json

[langgraph.json](../langgraph.json) registers two graphs:

| Graph id | Module | What it is |
|---|---|---|
| `support_desk` | `src/lcstack/capstone/server.py:graph` | the capstone |
| `scheduling_assistant` | `src/lcstack/scenarios/s22_deploying.py:graph` | scenario 22 |

Rules the server graphs follow:

- Compile **without** a checkpointer or store: the Agent Server supplies its own (Postgres in production).
- Per-run identity goes in `context` (the graph's `context_schema`), not in messages.
- Dependencies are the package itself (`"."`), so the image has exactly the pinned versions.

Commands:

```bash
pip install -e ".[dev]"
langgraph dev --no-browser          # local server on :2024 with an in-memory runtime, no API key
python scripts/agent_server_smoke.py   # what CI runs: threads, runs.wait, get_state through the SDK
langgraph dockerfile Dockerfile     # what `langgraph build` would build (scenario 22 generates it offline)
langgraph build -t lcdesk-agent-server   # needs Docker
```

## What the server needs

| Need | Why | In the Azure stack |
|---|---|---|
| `DATABASE_URI` (Postgres) | threads, runs, checkpoints, store | Postgres Flexible Server, URI in Key Vault |
| `REDIS_URI` | run queue and streaming between API and workers | Azure Cache for Redis, URI in Key Vault |
| `LANGSMITH_API_KEY` or a license key | the self-hosted Agent Server is licensed through LangSmith | Key Vault secret `langsmith-api-key`, written by an operator |
| `LANGSMITH_ENDPOINT` | where traces go (SaaS region or a self-hosted LangSmith) | app setting |
| Egress for license checks | the self-hosted server reports usage to LangChain's beacon endpoint unless an air-gapped license is used | allow outbound HTTPS from the environment |
| Always-on replicas | background workers run inside the server; scale-to-zero breaks queued and cron runs | `min_replicas >= 1`, enforced by a validation and a test |

Check the current LangChain documentation for licensing terms before choosing self-host; this repo does
not encode prices or license tiers.

## Managed versus self-hosted

| | Managed (LangSmith deployment) | Self-hosted (this repo's Azure templates) |
|---|---|---|
| Who runs Postgres, Redis, upgrades | LangChain | you |
| Data residency | the provider's regions | your subscription and region |
| Network | public endpoints with auth | can be fully private (VNet, private endpoints) |
| Identity | LangSmith workspace auth | your Entra ID, managed identity, Key Vault |
| Effort | lowest | highest; needs platform skills |
| When | prototypes, teams without a platform group | regulated clients, private networking, existing Azure landing zone |

LangChain recommends Kubernetes (Helm chart) for production self-hosting. Container Apps is used here
because it is the smaller footprint for a portfolio; for a client I would start from the Helm chart on AKS
when they already run AKS.

## Azure templates

| | Terraform | Bicep |
|---|---|---|
| Folder | [infra/terraform](../infra/terraform/README.md) | [infra/bicep](../infra/bicep/README.md) |
| Checks | fmt, validate, `terraform test` (3 runs, mocked providers), tflint, checkov | `bicep build` with the linter, warnings fail |

Resources: resource group, Log Analytics, user-assigned managed identity, Container Registry (no admin
user, AcrPull for the identity), Key Vault (RBAC, purge protection), Postgres Flexible Server (never public,
TLS required), Azure Cache for Redis (TLS 1.2, no non-TLS port), Container Apps environment and the Agent
Server app with Key Vault secret references. `private_networking = true` adds a VNet, NSGs, a delegated
Postgres subnet with a private DNS zone, private endpoints for Redis and Key Vault, internal-only ingress
and disables public access on the registry, vault and cache.

Known gaps are in [limitations.md](limitations.md#infrastructure).

## Workflows

| Workflow | Runs | Touches Azure |
|---|---|---|
| [ci.yml](../.github/workflows/ci.yml) | every push and PR | no |
| [infra.yml](../.github/workflows/infra.yml) | every push and PR | only `plan`, only if OIDC variables exist (they do not) |
| [deploy.yml](../.github/workflows/deploy.yml) | push to main | only if `DEPLOY_ENABLED == 'true'` (not set) |
| [teardown.yml](../.github/workflows/teardown.yml) | manual | same gate plus typed confirmation |

## One-time setup if someone does deploy it

1. Create an Entra app registration with a federated credential for this repo's `dev` and `prod`
   environments; grant it Contributor and User Access Administrator on the target resource groups.
2. Set repository variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
   `TFSTATE_RESOURCE_GROUP`, `TFSTATE_STORAGE_ACCOUNT`; create GitHub Environments `dev` and `prod`
   with required reviewers on `prod`.
3. Run provision once, then write the LangSmith key: `az keyvault secret set --vault-name <vault> -n langsmith-api-key --value <key>`.
4. Set `DEPLOY_ENABLED=true`. The deploy job builds the image with `langgraph build`, pushes it and rolls the app.
