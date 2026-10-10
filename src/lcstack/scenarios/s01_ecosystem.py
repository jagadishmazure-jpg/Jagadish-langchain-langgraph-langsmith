"""01 The Ecosystem: which package does what, proven against the installed versions.

Client: Wrenfield Grocers' platform team is standardising its agent stack and wants a dependency audit
that says, for every LangChain-family package, what it is for and whether the symbols the teams rely on
really live there in the installed version (not in a blog post from two versions ago).
"""

from __future__ import annotations

import importlib
from importlib.metadata import PackageNotFoundError, version

from lcstack.core.companies import RETAIL
from lcstack.scenarios import Meta

META = Meta(1, "The Ecosystem", "Package map: langchain, langchain-core, langgraph, langsmith, deepagents, integrations, langchain-classic",
            f"{RETAIL}: platform dependency audit", "retail", "ecosystem")  # fmt: skip

# distribution, role, symbol that must import, layer
PACKAGES = [
    ("langchain-core", "messages, runnables, tools, prompts (the shared base)", "langchain_core.runnables:Runnable", "base"),
    ("langchain", "create_agent and middleware, init_chat_model, init_embeddings", "langchain.agents:create_agent", "agents"),
    ("langgraph", "runtime: state graphs, checkpoints, interrupts, streaming", "langgraph.graph:StateGraph", "runtime"),
    ("langsmith", "tracing, datasets, evaluation, deployment client", "langsmith:Client", "observability"),
    ("deepagents", "planning, a virtual file system and sub-agents on top of create_agent", "deepagents:create_deep_agent", "agents"),
    ("langchain-openai", "integration: OpenAI and Azure OpenAI chat and embeddings", "langchain_openai:AzureChatOpenAI", "integration"),
    ("langchain-mcp-adapters", "integration: MCP servers as LangChain tools", "langchain_mcp_adapters.client:MultiServerMCPClient", "integration"),
    ("langchain-text-splitters", "document splitting for retrieval", "langchain_text_splitters:RecursiveCharacterTextSplitter", "retrieval"),
    ("langgraph-checkpoint-sqlite", "SqliteSaver for local single-process apps", "langgraph.checkpoint.sqlite:SqliteSaver", "persistence"),
    ("langgraph-checkpoint-postgres", "PostgresSaver for production", "langgraph.checkpoint.postgres:PostgresSaver", "persistence"),
    ("langchain-classic", "LEGACY: AgentExecutor, LLMChain, old memory classes", "langchain_classic.agents:AgentExecutor", "legacy"),
]


def audit() -> list[dict]:
    rows = []
    for dist, role, symbol, layer in PACKAGES:
        try:
            ver = version(dist)
        except PackageNotFoundError:
            ver = "not installed"
        mod, _, attr = symbol.partition(":")
        try:
            ok = hasattr(importlib.import_module(mod), attr)
        except ImportError:
            ok = False
        rows.append({"package": dist, "version": ver, "layer": layer, "role": role, "symbol": symbol, "importable": ok})
    return rows


def create_agent_is_a_graph() -> str:
    """create_agent returns a compiled LangGraph graph, which is why it inherits checkpoints and interrupts."""
    from langchain.agents import create_agent

    from lcstack.core.scripted import scripted

    agent = create_agent(scripted(), tools=[])
    return f"{type(agent).__module__}.{type(agent).__name__}"


def run() -> list[str]:
    out = [f"{RETAIL} - LangChain ecosystem audit (installed versions)", ""]
    out.append(f"{'package':<30} {'version':<10} {'layer':<13} symbol check")
    for r in audit():
        out.append(f"{r['package']:<30} {r['version']:<10} {r['layer']:<13} {r['symbol']} {'OK' if r['importable'] else 'MISSING'}")
    out += ["", f"create_agent(...) returns: {create_agent_is_a_graph()}",
            "Legacy chains and AgentExecutor import only from langchain_classic; new code uses create_agent or a graph."]  # fmt: skip
    return out
