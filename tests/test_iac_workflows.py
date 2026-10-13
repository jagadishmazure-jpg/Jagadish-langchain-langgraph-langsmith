"""Static checks on the IaC and the GitHub workflows (the terraform/checkov/tflint/bicep jobs run in CI)."""

import re
from pathlib import Path

import pytest
import yaml

TF = Path("infra/terraform")
BICEP = Path("infra/bicep/main.bicep").read_text()
WF = Path(".github/workflows")
SHA_PIN = re.compile(r"uses: [\w./-]+@[0-9a-f]{40} # v\d")


def tf() -> str:
    return "\n".join(p.read_text() for p in sorted(TF.glob("*.tf")))


def wf(name):
    d = yaml.safe_load((WF / name).read_text())
    d["on"] = d.pop(True, d.get("on"))
    return d


def test_stacks_have_the_same_components():
    for tf_type, bicep_type in [
        ('azurerm_container_app"', "Microsoft.App/containerApps"),
        ('azurerm_postgresql_flexible_server"', "Microsoft.DBforPostgreSQL/flexibleServers"),
        ('azurerm_redis_cache"', "Microsoft.Cache/redis"),
        ('azurerm_key_vault"', "Microsoft.KeyVault/vaults"),
        ('azurerm_user_assigned_identity"', "Microsoft.ManagedIdentity/userAssignedIdentities"),
        ('azurerm_private_endpoint"', "Microsoft.Network/privateEndpoints"),
    ]:
        assert tf_type in tf() and bicep_type in BICEP, tf_type


def test_langsmith_key_only_from_key_vault():
    assert "langsmith-api-key" in tf() and "langsmith-api-key" in BICEP
    assert not re.search(r'name\s*=\s*"LANGSMITH_API_KEY"\s*\n\s*value', tf())
    assert "{ name: 'LANGSMITH_API_KEY', secretRef: 'langsmith-api-key' }" in BICEP


def test_no_admin_credentials_and_tls_only():
    assert "admin_enabled                 = false" in tf() and "adminUserEnabled: false" in BICEP
    assert "non_ssl_port_enabled          = false" in tf() and "enableNonSslPort: false" in BICEP
    assert "require_secure_transport" in tf() and "require_secure_transport" in BICEP


def test_postgres_never_public():
    assert "public_network_access_enabled = false" in tf()
    assert BICEP.count("publicNetworkAccess: 'Disabled'") >= 2


def test_no_scale_to_zero():
    assert "var.min_replicas >= 1" in tf() and "@minValue(1)" in BICEP


def test_checkov_skips_are_documented():
    skips = re.findall(r"#checkov:skip=(CKV\w+):(.+)", tf())
    assert skips and all(len(reason.strip()) > 20 for _, reason in skips)


def test_terraform_tests_cover_dev_prod_and_validation():
    text = (TF / "tests/plan.tftest.hcl").read_text()
    for run in ('run "dev_defaults"', 'run "prod_private"', 'run "rejects_scale_to_zero"'):
        assert run in text


@pytest.mark.parametrize("name", sorted(p.name for p in WF.glob("*.yml")))
def test_workflow_hardening(name):
    d = wf(name)
    assert d["permissions"] == {"contents": "read"}, "top-level permissions must be read-only"
    text = (WF / name).read_text()
    for line in text.splitlines():
        if "uses:" in line and not line.strip().startswith("#"):
            assert SHA_PIN.search(line), f"{name}: action not pinned to a commit SHA: {line.strip()}"
    assert "client-secret" not in text and "AZURE_CLIENT_SECRET" not in text
    assert "LANGSMITH_API_KEY: ${{ secrets" not in text, "CI must not need a LangSmith key"


def test_ci_runs_everything_offline():
    text = (WF / "ci.yml").read_text()
    for step in ("pytest -q", "lcstack gate", "render_docs.py --check", "lint-imports", "postgres:17", "-m postgres",
                 "agent_server_smoke.py", "gitleaks", "sbom-action", "bicep build"):  # fmt: skip
        assert step in text, step


def test_deploy_is_gated_and_uses_oidc():
    jobs = wf("deploy.yml")["jobs"]
    for name in ("deploy-dev", "deploy-prod"):
        assert "vars.DEPLOY_ENABLED == 'true'" in jobs[name]["if"]
        assert jobs[name]["permissions"]["id-token"] == "write"
        assert any("azure/login" in s.get("uses", "") for s in jobs[name]["steps"])
    assert jobs["deploy-dev"]["environment"] == "dev" and jobs["deploy-prod"]["environment"] == "prod"
    assert "deploy-dev" in jobs["deploy-prod"]["needs"]


def test_teardown_needs_gate_and_confirmation():
    job = wf("teardown.yml")["jobs"]["teardown"]
    assert "vars.DEPLOY_ENABLED == 'true'" in job["if"] and "inputs.confirm == inputs.environment" in job["if"]


def test_codeql_and_dependabot():
    assert "python" in (WF / "codeql.yml").read_text() and "actions" in (WF / "codeql.yml").read_text()
    dep = Path(".github/dependabot.yml").read_text()
    for eco in ("pip", "github-actions", "terraform"):
        assert f"package-ecosystem: {eco}" in dep


def test_deploy_script_has_every_subcommand():
    text = Path(".github/scripts/deploy.sh").read_text()
    for sub in ("provision()", "image()", "smoke()", "destroy()"):
        assert sub in text
