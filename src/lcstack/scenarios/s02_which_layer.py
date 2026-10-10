"""02 Which Layer to Use: one task built five ways, and a chooser that picks the highest layer that fits.

Client: Kestrel Ridge Bank's card-dispute intake. A customer message has to be classified (fraud,
not-received, duplicate, other) and acknowledged. The team asked which LangChain layer to standardise
on, so the same task is implemented with model + LCEL, create_agent, a deep agent, the Graph API and the
Functional API, and each version reports how much machinery it brings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypedDict

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.func import entrypoint, task
from langgraph.graph import END, START, StateGraph

from lcstack.core.companies import BANKING
from lcstack.core.scripted import Intent, Playbook, ScriptedChatModel, Turn, scripted
from lcstack.scenarios import Meta

META = Meta(2, "Which Layer to Use", "Model+LCEL vs create_agent vs deep agents vs Graph API vs Functional API, plus a layer chooser",
            f"{BANKING}: card-dispute intake built five ways", "banking", "which-layer")  # fmt: skip

MESSAGE = "I never authorised the 89.00 charge from a store in another country, my card is still in my wallet"
RULES = [("fraud", r"never authori[sz]ed|didn.t make|stolen|not me"), ("not_received", r"never (arrived|received)|didn.t arrive"),
         ("duplicate", r"twice|duplicate|charged two")]  # fmt: skip


def classify(text: str) -> str:
    return next((label for label, pat in RULES if re.search(pat, text, re.I)), "other")


def ack(label: str) -> str:
    return f"Dispute logged as {label}. A specialist will review it within two business days."


def _answer(t: Turn) -> str:
    label = t.results.get("classify_dispute") or classify(t.last_human)
    return ack(label)


PLAYBOOK = Playbook(
    intents=[
        Intent(
            "dispute",
            r".",
            answer=_answer,
            steps=[
                lambda t: ("classify_dispute", {"text": t.last_human}),
                # only a deep agent offers a file system: it files a case note before answering
                lambda t: (
                    (
                        "write_file",
                        {
                            "file_path": "/disputes/case-note.md",
                            "content": f"Dispute type: {t.results.get('classify_dispute')}\nCustomer text: {t.last_human}",
                        },
                    )
                    if "classify_dispute" in t.results
                    else None
                ),
            ],
        ),
    ]
)


@tool
def classify_dispute(text: str) -> str:
    """Classify a card dispute as fraud, not_received, duplicate or other."""
    return classify(text)


def model() -> ScriptedChatModel:
    return scripted(PLAYBOOK, name="dispute-model")


# 1. Model + LCEL: one call in a fixed pipeline
def via_lcel(m: ScriptedChatModel) -> str:
    prompt = ChatPromptTemplate.from_messages([("system", "Classify and acknowledge card disputes."), ("human", "{text}")])
    return (prompt | m | StrOutputParser()).invoke({"text": MESSAGE})


# 2. create_agent: standard tool-calling loop
def via_create_agent(m: ScriptedChatModel) -> str:
    agent = create_agent(m, [classify_dispute], system_prompt="You handle card disputes.")
    return agent.invoke({"messages": [{"role": "user", "content": MESSAGE}]})["messages"][-1].content


# 3. Deep agent: planning tool, virtual files and sub-agents on top of create_agent
def via_deep_agent(m: ScriptedChatModel) -> str:
    from deepagents import create_deep_agent

    agent = create_deep_agent(model=m, tools=[classify_dispute], system_prompt="You handle card disputes.")
    state = agent.invoke({"messages": [{"role": "user", "content": MESSAGE}]})
    LAST_DEEP_FILES[:] = sorted(state.get("files", {}))
    return state["messages"][-1].content


LAST_DEEP_FILES: list[str] = []


# 4. Graph API: explicit nodes and edges
class DisputeState(TypedDict, total=False):
    text: str
    label: str
    reply: str


def via_graph(m: ScriptedChatModel) -> str:
    b = StateGraph(DisputeState)
    b.add_node("classify", lambda s: {"label": classify(s["text"])})
    b.add_node("acknowledge", lambda s: {"reply": m.invoke(f"Acknowledge a {s['label']} dispute: {s['text']}").content})
    b.add_edge(START, "classify")
    b.add_edge("classify", "acknowledge")
    b.add_edge("acknowledge", END)
    return b.compile().invoke({"text": MESSAGE})["reply"]


# 5. Functional API: durable workflow as plain Python
@task
def classify_task(text: str) -> str:
    return classify(text)


@task
def draft_task(m: ScriptedChatModel, label: str, text: str) -> str:
    return m.invoke(f"Acknowledge a {label} dispute: {text}").content


def via_functional(m: ScriptedChatModel) -> str:
    @entrypoint(checkpointer=InMemorySaver())
    def dispute_workflow(text: str) -> str:
        label = classify_task(text).result()
        return draft_task(m, label, text).result()

    return dispute_workflow.invoke(MESSAGE, {"configurable": {"thread_id": "dispute-1"}})


IMPLEMENTATIONS = {"Model + LCEL": via_lcel, "create_agent": via_create_agent, "Deep agent": via_deep_agent,
                   "Graph API": via_graph, "Functional API": via_functional}  # fmt: skip


@dataclass
class Needs:
    tools: bool = False
    long_running_plan: bool = False
    custom_control_flow: bool = False
    durable_plain_python: bool = False


def choose_layer(n: Needs) -> str:
    """Start high, drop down only for control you actually need."""
    if n.custom_control_flow:
        return "Graph API"
    if n.durable_plain_python:
        return "Functional API"
    if n.long_running_plan:
        return "Deep agent"
    if n.tools:
        return "create_agent"
    return "Model + LCEL"


def run() -> list[str]:
    out = [f"{BANKING} - one dispute, five layers", f'input: "{MESSAGE}"', ""]
    out.append(f"{'layer':<15} {'model calls':>11} {'tools offered':>13}  reply")
    for name, fn in IMPLEMENTATIONS.items():
        m = model()
        reply = fn(m)
        out.append(f"{name:<15} {m.calls:>11} {len(m.tools_seen):>13}  {reply}")
    out.append(f"deep agent virtual files written: {LAST_DEEP_FILES}")
    out += ["", "layer chooser:"]
    for label, needs in [("summarise a statement", Needs()), ("look up and refund", Needs(tools=True)),
                         ("multi-day collections plan", Needs(tools=True, long_running_plan=True)),
                         ("nightly batch with retries", Needs(durable_plain_python=True)),
                         ("dispute with approvals and loops", Needs(tools=True, custom_control_flow=True))]:  # fmt: skip
        out.append(f"  {label:<34} -> {choose_layer(needs)}")
    return out
