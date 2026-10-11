"""25 Import Map: where things live in 1.x, verified, plus a linter for pre-1.0 imports.

Client: Quillmere Home Loans has a dozen internal agent repos written against older tutorials. Their
platform team wants (a) a cheat table of where each building block lives now, checked against the
installed versions rather than memory, and (b) ``lcstack lint-imports`` to flag old imports in CI.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

from lcstack.core.companies import MORTGAGE
from lcstack.scenarios import Meta

META = Meta(25, "Import Map", "Where each building block lives in 1.x (verified by import), and an AST linter that flags pre-1.0 imports",
            f"{MORTGAGE}: import audit across internal agent repos", "mortgage", "import-map")  # fmt: skip

IMPORT_MAP = [
    ("Agents, middleware", "langchain.agents", ["create_agent", "AgentState"]),
    ("Agents, middleware", "langchain.agents.middleware", ["HumanInTheLoopMiddleware", "PIIMiddleware", "before_model", "wrap_tool_call"]),
    ("Models, embeddings", "langchain.chat_models", ["init_chat_model"]),
    ("Models, embeddings", "langchain.embeddings", ["init_embeddings"]),
    ("Tools", "langchain.tools", ["tool", "ToolRuntime", "ToolException"]),
    ("Prompts, parsers", "langchain_core.prompts", ["ChatPromptTemplate", "MessagesPlaceholder"]),
    ("Prompts, parsers", "langchain_core.output_parsers", ["StrOutputParser", "PydanticOutputParser"]),
    ("Messages", "langchain_core.messages", ["HumanMessage", "AIMessage", "ToolMessage", "trim_messages"]),
    ("Graph, state", "langgraph.graph", ["StateGraph", "MessagesState", "START", "END"]),
    ("Graph, state", "langgraph.graph.message", ["add_messages"]),
    ("Command, Send, interrupt", "langgraph.types", ["Command", "Send", "interrupt", "Overwrite"]),
    ("Functional API", "langgraph.func", ["entrypoint", "task"]),
    ("Prebuilt graph parts", "langgraph.prebuilt", ["ToolNode", "tools_condition"]),
    ("Checkpointers", "langgraph.checkpoint.memory", ["InMemorySaver"]),
    ("Checkpointers", "langgraph.checkpoint.sqlite", ["SqliteSaver"]),
    ("Checkpointers", "langgraph.checkpoint.postgres", ["PostgresSaver"]),
    ("Stores", "langgraph.store.memory", ["InMemoryStore"]),
    ("Runtime context", "langgraph.runtime", ["Runtime"]),
    ("Tracing, evaluation", "langsmith", ["traceable", "Client", "evaluate"]),
    ("MCP tools", "langchain_mcp_adapters.client", ["MultiServerMCPClient"]),
    ("Legacy (only for migration)", "langchain_classic.agents", ["AgentExecutor"]),
]

# (module prefix, names or None for any) -> advice
RULES = [
    (
        "langchain.agents",
        {"AgentExecutor", "initialize_agent", "create_tool_calling_agent", "create_openai_functions_agent"},
        "use langchain.agents.create_agent",
    ),
    ("langgraph.prebuilt", {"create_react_agent"}, "use langchain.agents.create_agent (with middleware)"),
    ("langchain.chains", None, "use an LCEL pipe or an agent with a retriever tool (old chains live in langchain_classic)"),
    ("langchain.memory", None, "use a checkpointer plus thread_id"),
    ("langchain.llms", None, "use init_chat_model or the provider package (langchain_openai, ...)"),
    ("langchain.chat_models", {"ChatOpenAI", "AzureChatOpenAI", "ChatAnthropic"}, "import the class from its provider package"),
    ("langchain_classic", None, "legacy package: allowed only in clearly labelled legacy code"),
]


def verify_map() -> list[tuple[str, str, int, int]]:
    rows = []
    for need, module, names in IMPORT_MAP:
        try:
            mod = importlib.import_module(module)
            ok = sum(hasattr(mod, n) for n in names)
        except ImportError:
            ok = 0
        rows.append((need, module, ok, len(names)))
    return rows


def lint_source(src: str, filename: str = "<src>") -> list[str]:
    findings = []
    for node in ast.walk(ast.parse(src, filename)):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods, names = [node.module], {a.name for a in node.names}
        elif isinstance(node, ast.Import):
            mods, names = [a.name for a in node.names], set()
        else:
            continue
        for mod in mods:
            for prefix, bad, advice in RULES:
                if (mod == prefix or mod.startswith(prefix + ".")) and (bad is None or names & bad):
                    findings.append(f"{filename}:{node.lineno}: {mod} -> {advice}")
    return findings


def lint_paths(paths: list[str]) -> tuple[list[str], int]:
    lines, bad = [], 0
    for p in paths:
        for f in sorted(Path(p).rglob("*.py")) if Path(p).is_dir() else [Path(p)]:
            found = lint_source(f.read_text(), f.as_posix())
            bad += len(found)
            lines += found
    lines.append(f"{bad} pre-1.0 import(s) found")
    return lines, bad


OLD_SERVICE = """from langchain.agents import initialize_agent, AgentExecutor
from langchain.chains import RetrievalQA
from langchain.memory import ConversationBufferMemory
from langchain.chat_models import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate
"""


def run() -> list[str]:
    out = [f"{MORTGAGE} - import map for LangChain / LangGraph / LangSmith 1.x", ""]
    out.append(f"{'need':<28} {'import from':<32} names found")
    for need, module, ok, n in verify_map():
        out.append(f"{need:<28} {module:<32} {ok}/{n}")
    out += ["", "lint of a pre-1.0 Quillmere service (rate_lock_bot.py):"]
    out += [f"  {x}" for x in lint_source(OLD_SERVICE, "rate_lock_bot.py")]
    here = Path(__file__).resolve().parents[1]
    _, n_new = lint_paths([str(here / "scenarios"), str(here / "capstone"), str(here / "core")])
    _, n_legacy = lint_paths([str(here / "legacy")])
    out.append(f"this repo: {n_new} pre-1.0 imports in scenarios/capstone/core; {n_legacy} in the labelled legacy folder (expected)")
    return out
