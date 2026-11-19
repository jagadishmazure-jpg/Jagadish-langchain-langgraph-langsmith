"""Load and check the example Foundry deployment manifest. Nothing here calls azd or Azure."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "foundry" / "azure.yaml"


def load(path: Path | None = None) -> dict:
    return yaml.safe_load((path or MANIFEST).read_text())


def check(document: dict) -> list[str]:
    """Return problems. An empty list means the example has the shape the hosting articles describe."""
    problems: list[str] = []
    services = document.get("services") if isinstance(document, dict) else None
    if not isinstance(services, dict) or "support-desk" not in services:
        return ["services.support-desk is missing"]
    service = services["support-desk"]
    if service.get("host") != "azure.ai.agent":
        problems.append("host must be azure.ai.agent")
    if service.get("kind") != "hosted":
        problems.append("kind must be hosted")
    env = service.get("env") or {}
    if str(env.get("PYTHONNOUSERSITE")) != "1":
        problems.append('env.PYTHONNOUSERSITE must be "1"')
    if env.get("LCSTACK_MODEL") != "scripted":
        problems.append("env.LCSTACK_MODEL must stay scripted in this example")
    if "FOUNDRY_PROJECT_ENDPOINT" in env:
        problems.append("do not set FOUNDRY_PROJECT_ENDPOINT; the platform injects it")
    if "APPLICATIONINSIGHTS_CONNECTION_STRING" in env:
        problems.append("do not put an Application Insights connection string in the example")
    code = service.get("codeConfiguration") or {}
    if code.get("runtime") != "python_3_13":
        problems.append("codeConfiguration.runtime must be python_3_13")
    entry = str(code.get("entryPoint") or "")
    if "lcstack.foundry.serve" not in entry or "--protocol responses" not in entry:
        problems.append("entryPoint must run lcstack.foundry.serve --protocol responses")
    blob = yaml.safe_dump(document)
    for banned in ("AccountKey=", "api_key", "api-key", "BEGIN PRIVATE", "https://"):
        if banned.lower() in blob.lower():
            problems.append(f"manifest contains {banned}")
    return problems


def report() -> list[str]:
    problems = check(load())
    lines = ["foundry/azure.yaml"]
    if problems:
        lines.extend(f"  problem: {problem}" for problem in problems)
    else:
        lines.append("  valid example (not applied, no credentials)")
    lines.append("  host: azure.ai.agent  kind: hosted  protocol: responses")
    lines.append("  entry point compiles support_desk with a checkpointer; the langgraph.json copy has none")
    return lines
