"""19 Subgraphs and Multi-Agent: compose graphs like functions; supervisor routing and handoffs.

Client: Ferrowind Insurance's customer-service desk. A supervisor reads each message and delegates to a
claims, policy or billing specialist (each its own agent, added to the parent as a node). When the
claims agent learns that a payment is overdue it hands the conversation to billing with
``Command(goto=..., graph=Command.PARENT)``. A fraud-check subgraph keeps its working signals private.
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command
from pydantic import BaseModel

from lcstack.core.companies import INSURANCE
from lcstack.core.scripted import Intent, Playbook, Turn, scripted
from lcstack.scenarios import Meta

META = Meta(19, "Subgraphs and Multi-Agent", "Compiled agents as nodes, a structured-output supervisor router, handoff with Command.PARENT, subgraph private state",
            f"{INSURANCE}: supervisor with claims, policy and billing specialists", "insurance", "multi-agent")  # fmt: skip


class Route(BaseModel):
    """Which specialist should handle the latest message."""

    specialist: Literal["claims_agent", "policy_agent", "billing_agent"]
    reason: str


def _route(t: Turn) -> dict:
    text = t.last_human.lower()
    who = (
        "billing_agent"
        if re.search(r"pay|bill|premium due", text)
        else "policy_agent"
        if re.search(r"cover|policy|deductible", text)
        else "claims_agent"
    )
    return {"specialist": who, "reason": f"keywords in: {text[:40]}"}


@tool
def claim_status(claim_id: str) -> str:
    """Status of a claim."""
    return f"{claim_id}: approved, payment on hold because the policy premium is overdue"


@tool
def transfer_to_billing(reason: str, runtime: ToolRuntime) -> Command:
    """Hand the conversation to the billing specialist."""
    note = ToolMessage(f"Transferred to billing: {reason}", tool_call_id=runtime.tool_call_id)
    return Command(
        goto="billing_agent", graph=Command.PARENT, update={"messages": [*runtime.state["messages"], note], "handoffs": ["claims->billing"]}
    )


@tool
def coverage(question: str) -> str:
    """Answer coverage questions from the policy wording."""
    return "Water damage from a sudden pipe burst is covered; gradual leaks are excluded."


@tool
def balance(policy_id: str) -> str:
    """Outstanding premium for a policy."""
    return f"{policy_id}: 182.50 overdue; paying it releases any held claim payments within 1 business day"


CLAIMS = Playbook(intents=[Intent("status", r".", steps=[
    lambda t: ("claim_status", {"claim_id": "CL-7781"}),
    lambda t: ("transfer_to_billing", {"reason": "claim payment held for overdue premium"}) if "overdue" in t.results.get("claim_status", "") else None,
], answer=lambda t: t.results.get("claim_status", ""))])  # fmt: skip
POLICY = Playbook(intents=[Intent("cover", r".", steps=[lambda t: ("coverage", {"question": t.last_human})], answer=lambda t: t.results["coverage"])])
BILLING = Playbook(intents=[Intent("bill", r".", steps=[lambda t: ("balance", {"policy_id": "FW-HO-3381"})],
                                   answer=lambda t: f"Billing here: {t.results['balance']}.")])  # fmt: skip


class Desk(MessagesState):
    handoffs: list[str]
    route: str


class FraudState(TypedDict, total=False):
    messages: list  # shared with the parent (same key name)
    signals: list[str]  # private: the parent has no such key, so it never leaks upward
    fraud_flag: bool


def fraud_subgraph():
    b = StateGraph(FraudState)
    b.add_node("collect", lambda s: {"signals": ["new policy", "high amount"] if "fire" in str(s["messages"][-1].content).lower() else []})
    b.add_node("score", lambda s: {"fraud_flag": len(s["signals"]) >= 2})
    b.add_edge(START, "collect")
    b.add_edge("collect", "score")
    b.add_edge("score", END)
    return b.compile()


def build():
    router = scripted(Playbook(extractors={"Route": _route}), name="supervisor").with_structured_output(Route)

    def supervisor(state: Desk) -> Command[Literal["claims_agent", "policy_agent", "billing_agent"]]:
        r = router.invoke(state["messages"][-1].content)
        return Command(goto=r.specialist, update={"route": r.specialist})

    b = StateGraph(Desk)
    b.add_node("supervisor", supervisor)
    b.add_node("claims_agent", create_agent(scripted(CLAIMS, name="claims"), [claim_status, transfer_to_billing], name="claims_agent"),
               destinations=("billing_agent",))  # fmt: skip
    b.add_node("policy_agent", create_agent(scripted(POLICY, name="policy"), [coverage], name="policy_agent"))
    b.add_node("billing_agent", create_agent(scripted(BILLING, name="billing"), [balance], name="billing_agent"))
    b.add_edge(START, "supervisor")
    b.add_edge("policy_agent", END)
    b.add_edge("billing_agent", END)
    return b.compile(checkpointer=InMemorySaver())


def run() -> list[str]:
    g = build()
    out = [f"{INSURANCE} - supervisor and specialists", ""]
    for i, ask in enumerate(
        ["Is a burst pipe covered by my policy?", "When is my premium due and what do I owe?", "What's happening with claim CL-7781?"]
    ):
        r = g.invoke({"messages": [{"role": "user", "content": ask}], "handoffs": []}, {"configurable": {"thread_id": f"desk-{i}"}})
        out.append(f"Q: {ask}")
        out.append(f"   routed to {r['route']}; handoffs={r.get('handoffs') or []}")
        out.append(f"   A: {r['messages'][-1].content}")
    parent = StateGraph(MessagesState)
    parent.add_node("fraud_check", fraud_subgraph())
    parent.add_edge(START, "fraud_check")
    res = parent.compile().invoke({"messages": [{"role": "user", "content": "Car fire last night, policy is 9 days old"}]})
    out += ["", f"fraud subgraph as a node: parent state keys after the run = {sorted(res)} (private 'signals' and 'fraud_flag' stay inside)"]
    return out
