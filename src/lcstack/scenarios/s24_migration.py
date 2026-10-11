"""24 Migrating Old Code: pre-1.0 patterns and their replacements, with behaviour parity checked.

Client: Ferrowind Insurance's FNOL bot was written with AgentExecutor, LLMChain and
ConversationBufferMemory. The migration moves it to create_agent, an LCEL pipe and a checkpointer with
thread_id, and proves that the same input produces the same tool calls and answers. The legacy code is
kept, clearly labelled, in src/lcstack/legacy/.
"""

from __future__ import annotations

import re
import warnings
import zlib

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from lcstack.core.companies import INSURANCE
from lcstack.core.persist import memory_saver
from lcstack.core.scripted import Intent, Playbook, Turn, scripted
from lcstack.scenarios import Meta

META = Meta(24, "Migrating Old Code", "AgentExecutor -> create_agent, LLMChain -> LCEL, ConversationBufferMemory -> checkpointer + thread_id, legacy imports -> langchain-classic",
            f"{INSURANCE}: FNOL bot migrated from AgentExecutor", "insurance", "migration")  # fmt: skip

MAPPING = [
    ("initialize_agent, AgentExecutor", "langchain.agents.create_agent"),
    ("langgraph.prebuilt.create_react_agent", "create_agent with middleware"),
    ("LLMChain, RetrievalQA", "LCEL pipes, or an agent with a retriever tool"),
    ("ConversationBufferMemory", "a checkpointer plus thread_id"),
    ("legacy chains and imports", "the langchain-classic package"),
]


@tool
def open_claim(policy_id: str, loss_type: str) -> str:
    """Open a new claim on a policy."""
    return f"Claim CL-{zlib.crc32(f'{policy_id}|{loss_type}'.encode()) % 9000 + 1000} opened on {policy_id} for {loss_type}"


@tool
def check_policy(policy_id: str) -> str:
    """Check a policy is in force."""
    return f"{policy_id}: in force, deductible 500.00"


def _pid(t: Turn) -> str:
    for m in reversed(t.messages):
        found = re.search(r"FW-[A-Z]{2}-\d+", str(m.content))
        if found:
            return found.group(0)
    return ""


PLAYBOOK = Playbook(
    intents=[
        Intent("summary", r"Summarize", answer=lambda t: "Hail damage to roof and car; policy in force; claim opened."),
        Intent("followup", r"which policy|what policy", answer=lambda t: f"You reported on policy {_pid(t) or 'unknown'}."),
        Intent("fnol", r"report|hail|crash|water", steps=[
            lambda t: ("check_policy", {"policy_id": _pid(t)}),
            lambda t: ("open_claim", {"policy_id": _pid(t), "loss_type": "hail" if "hail" in t.last_human.lower() else "other"}),
        ], answer=lambda t: f"{t.results['open_claim'].split(' opened')[0]} is open. {t.results['check_policy'].split(': ')[1].capitalize()}."),
    ]
)  # fmt: skip


def legacy_run(question: str, followup: str) -> dict:
    from lcstack.legacy.fnol_bot import legacy_executor, legacy_summary_chain

    model = scripted(PLAYBOOK, name="legacy")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ex = legacy_executor(model, [check_policy, open_claim])
        first = ex.invoke({"input": question})
        second = ex.invoke({"input": followup})
        summary = legacy_summary_chain(model).invoke({"text": question})["text"]
    calls = [(a.tool, a.tool_input) for a, _ in first["intermediate_steps"]]
    return {"calls": calls, "answer": first["output"], "followup": second["output"], "summary": summary}


def modern_run(question: str, followup: str) -> dict:
    model = scripted(PLAYBOOK, name="modern")
    agent = create_agent(
        model, [check_policy, open_claim], system_prompt="You take first notice of loss for Ferrowind Insurance.", checkpointer=memory_saver()
    )
    cfg = {"configurable": {"thread_id": "fnol-1"}}
    first = agent.invoke({"messages": [{"role": "user", "content": question}]}, cfg)
    second = agent.invoke({"messages": [{"role": "user", "content": followup}]}, cfg)
    summary = (PromptTemplate.from_template("Summarize this claim for the adjuster: {text}") | model | StrOutputParser()).invoke({"text": question})
    calls = [(tc["name"], tc["args"]) for m in first["messages"] for tc in getattr(m, "tool_calls", [])]
    return {"calls": calls, "answer": first["messages"][-1].content, "followup": second["messages"][-1].content, "summary": summary}


def run() -> list[str]:
    q, f = "Hail hit my roof and car last night, I want to report it. Policy FW-HO-2207.", "Which policy did I report on?"
    old, new = legacy_run(q, f), modern_run(q, f)
    out = [f"{INSURANCE} - FNOL bot migration parity", ""]
    out.append(f"{'old pattern':<40} new pattern")
    out += [f"{a:<40} {b}" for a, b in MAPPING]
    out.append("")
    for key in ("calls", "answer", "followup", "summary"):
        same = old[key] == new[key]
        out.append(f"{key:<9} {'SAME' if same else 'DIFFERENT'}: {new[key]}")
    return out
