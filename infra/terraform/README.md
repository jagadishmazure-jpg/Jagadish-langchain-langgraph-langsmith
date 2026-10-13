# infra/terraform

| File | What it does |
|---|---|
| `versions.tf`, `providers.tf`, `backend.tf` | azurerm and random providers; remote state with Entra auth |
| `variables.tf`, `locals.tf` | inputs (environment, image, private networking, replicas, SKUs) and naming |
| `main.tf` | resource group, Log Analytics, managed identity, registry, Key Vault, Postgres, Redis, Container Apps |
| `network.tf` | private networking option: VNet, subnets with NSGs, Postgres private DNS, private endpoints |
| `outputs.tf` | names the deploy script needs |
| `envs/` | `dev.tfvars` (public, Basic SKUs), `prod.tfvars` (private, Premium Redis), backend keys |
| `tests/plan.tftest.hcl` | offline plan tests with mocked providers: dev defaults, prod private, scale-to-zero rejected |
| `.tflint.hcl` | tflint with the azurerm ruleset |

```bash
terraform init -backend=false && terraform validate && terraform test
tflint --init && tflint --recursive
checkov -d . --config-file ../../.checkov.yaml
```

checkov skips are inline (`#checkov:skip=ID:reason`) and each states why; most depend on
`private_networking` or Premium SKUs that checkov cannot evaluate statically.
