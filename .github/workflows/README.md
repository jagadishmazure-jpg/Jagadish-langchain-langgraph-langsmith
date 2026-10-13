# workflows

| File | What it does |
|---|---|
| `ci.yml` | lint, import lint, tests, regression gate, doc drift, PostgresSaver on a service container, Agent Server smoke, Bicep build, SBOM, gitleaks |
| `codeql.yml` | CodeQL for Python and for the workflows |
| `infra.yml` | terraform fmt/validate/test, tflint, checkov; plan only if Azure OIDC variables exist |
| `deploy.yml` | gated by `DEPLOY_ENABLED` (not set): provision, build and push the Agent Server image, smoke |
| `teardown.yml` | gated, manual, typed confirmation |
