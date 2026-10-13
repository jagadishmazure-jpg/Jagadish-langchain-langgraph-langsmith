# Security policy

## Scope

Offline code, fictional companies and synthetic data for LangChain, LangGraph and LangSmith patterns, plus
infrastructure templates that have never been deployed. The repository holds no credentials, API keys,
tenant or subscription identifiers, or real customer data, and its tests enforce that.

## Reporting a vulnerability

1. Open a private security advisory on GitHub (Security tab, "Report a vulnerability"). Include the file,
   the problem and how to reproduce it.
2. If that button is not shown, open an issue titled `Security contact request` with no technical details,
   and I will reply with a private channel.

I aim to acknowledge a report within 5 working days. This is a personal portfolio maintained by one person,
so there is no formal SLA or bug bounty.

## Design choices that matter for security

- **No keys anywhere.** Models run scripted offline; the real-model switch uses an Entra ID token; LangSmith
  tracing needs both switches; CI uses OIDC and needs no secrets.
- **Untrusted text is data.** Customer messages, tool outputs and retrieved documents are screened;
  injected lines are quarantined; the v2 prompt says so; attack cases are in the dataset and gated at 1.0.
- **Agents are constrained.** Per-agent tool allowlists, identity from run context, human approval for
  money movement and card orders, output validation and PII masking (including in traces).
- **Supply chain:** pinned lockfile, SHA-pinned actions, Dependabot, CodeQL (Python and Actions), gitleaks
  over full history, an SPDX SBOM, checkov and tflint on Terraform.
- **Deployment gated off** until `DEPLOY_ENABLED` is set; prod needs environment reviewers.
- **GitHub settings:** secret scanning with push protection, Dependabot alerts and security updates, private
  vulnerability reporting, and rulesets on `main` that block force-pushes and deletion and require the CI
  checks for pull requests. The maintainer (admin) can still push directly, so for direct pushes the checks
  run after the push.

Threat model: [docs/security.md](docs/security.md).

## Supported versions

Only the `main` branch is maintained.
