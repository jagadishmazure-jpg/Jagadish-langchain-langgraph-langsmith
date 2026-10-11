"""22 Deploying: from notebook to server with langgraph.json, langgraph dev and langgraph build.

Client: Halsey Vale Health wants its appointment-scheduling assistant behind an HTTP API (threads,
runs, streaming, cron) that the patient portal can call. This scenario validates the deployment
configuration and builds the Dockerfile offline; CI then starts the real Agent Server with
``langgraph dev`` and drives it with the SDK (scripts/agent_server_smoke.py). Nothing is deployed to a
cloud: the managed (LangSmith Deployment) and self-hosted (container + Postgres + Redis) paths are
documented in docs/deployment.md, and the Azure Container Apps IaC is written but not applied.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from langchain.agents import create_agent

from lcstack.core.companies import HEALTHCARE
from lcstack.core.scripted import scripted
from lcstack.scenarios import Meta
from lcstack.scenarios.s17_long_term_memory import PLAYBOOK, Patient, find_slots, recall_preferences

META = Meta(22, "Deploying", "langgraph.json, a server-ready graph (no checkpointer: the server provides one), langgraph dockerfile/build, SDK threads/runs/crons, managed vs self-host",
            f"{HEALTHCARE}: scheduling assistant behind the Agent Server API", "healthcare", "deploying")  # fmt: skip

ROOT = Path(__file__).resolve().parents[3]

# The server injects its own checkpointer and store (Postgres in production), so the exported graph has none.
graph = create_agent(scripted(PLAYBOOK, name="scheduler"), [recall_preferences, find_slots], context_schema=Patient, name="scheduling_assistant")

SDK_SURFACE = {
    "assistants": ["search", "get", "create", "update"],
    "threads": ["create", "get", "get_state", "update_state", "get_history", "search"],
    "runs": ["create", "wait", "stream", "join", "cancel", "list"],
    "crons": ["create", "create_for_thread", "search", "delete"],
    "store": ["put_item", "get_item", "search_items", "delete_item"],
}


def load_graph(spec: str):
    path, _, attr = spec.partition(":")
    mod_path = (ROOT / path).resolve()
    module_spec = importlib.util.spec_from_file_location(f"lgjson_{mod_path.stem}", mod_path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return getattr(module, attr)


def run() -> list[str]:
    from langgraph_cli.config import config_to_docker, validate_config_file
    from langgraph_sdk import get_client

    cfg_path = ROOT / "langgraph.json"
    config = validate_config_file(cfg_path)
    out = [
        f"{HEALTHCARE} - Agent Server deployment check (offline)",
        "",
        f"langgraph.json validated by langgraph-cli: python {config['python_version']}, {len(config['graphs'])} graphs",
    ]
    for name, spec in json.loads(cfg_path.read_text())["graphs"].items():
        g = load_graph(spec)
        nodes = [n for n in g.get_graph().nodes if not n.startswith("__")]
        out.append(
            f"  {name:<22} {type(g).__name__}, nodes={nodes}, checkpointer={'none (server provides it)' if g.checkpointer is None else 'SET - remove it'}"
        )
    dockerfile, _ = config_to_docker(cfg_path, config)
    lines = dockerfile.splitlines()
    out += ["", "Dockerfile generated (what `langgraph build` would build):"]
    out += [f"  {line}" for line in lines if line.startswith(("FROM", "WORKDIR"))]
    out.append(
        f"  {sum(1 for line in lines if line.startswith(('RUN', 'ADD', 'ENV')))} RUN/ADD/ENV instructions; graphs registered via LANGSERVE_GRAPHS"
    )
    client = get_client(url="http://127.0.0.1:2024")  # constructing the client makes no request
    out += ["", "SDK surface used by the portal (checked against the installed langgraph-sdk):"]
    for group, methods in SDK_SURFACE.items():
        sub = getattr(client, group)
        out.append(f"  client.{group:<10} {', '.join(m for m in methods if hasattr(sub, m))}")
    out += ["", "self-host needs: DATABASE_URI (Postgres), REDIS_URI (Redis), LANGGRAPH_CLOUD_LICENSE_KEY and/or LANGSMITH_API_KEY",
            "managed (LangSmith Deployment): push the repo, LangSmith builds the same image and provides Postgres and Redis"]  # fmt: skip
    return out
