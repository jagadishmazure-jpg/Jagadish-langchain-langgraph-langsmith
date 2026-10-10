"""13 A ReAct Graph by Hand: model node, ToolNode, tools_condition, and the loop between them.

Client: Ferrowind Insurance's policy-servicing assistant. The platform team wanted to see exactly what
create_agent does before adopting it, so the same agent is built by hand with StateGraph and compared
call for call with create_agent.
"""

from __future__ import annotations

import re

from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from lcstack.core.companies import INSURANCE
from lcstack.core.scripted import Intent, Playbook, Turn, scripted
from lcstack.scenarios import Meta

META = Meta(13, "A ReAct Graph by Hand", "StateGraph(MessagesState) + bind_tools + ToolNode + tools_condition + checkpointer, compared with create_agent",
            f"{INSURANCE}: policy-servicing assistant", "insurance", "react-by-hand")  # fmt: skip

POLICIES = {"FW-HO-3381": {"holder": "R. Okafor", "type": "homeowners", "renewal": "in 23 days", "premium": 1420.00}}


@tool
def get_policy(policy_id: str) -> str:
    """Return the holder, type, renewal and premium of a policy."""
    p = POLICIES.get(policy_id)
    return f"{policy_id}: {p}" if p else f"ERROR: unknown policy {policy_id}"


@tool
def quote_renewal(policy_id: str, add_flood: bool = False) -> str:
    """Quote the renewal premium, optionally with flood cover."""
    base = POLICIES[policy_id]["premium"] * 1.04
    return f"{policy_id} renewal: {base + (310.0 if add_flood else 0):.2f}"


def _pid(t: Turn) -> str:
    m = re.search(r"FW-HO-\d+", t.last_human)
    return m.group(0) if m else ""


PLAYBOOK = Playbook(intents=[Intent("renewal", r"renew", steps=[
    lambda t: ("get_policy", {"policy_id": _pid(t)}),
    lambda t: ("quote_renewal", {"policy_id": _pid(t), "add_flood": "flood" in t.last_human.lower()}),
], answer=lambda t: f"Your policy renews {POLICIES[_pid(t)]['renewal']}; {t.results['quote_renewal'].split(': ')[1]} including the options you asked for.")])  # fmt: skip

TOOLS = [get_policy, quote_renewal]


def build_by_hand(model):
    llm = model.bind_tools(TOOLS)

    def agent(state: MessagesState) -> dict:
        return {"messages": [llm.invoke(state["messages"])]}

    b = StateGraph(MessagesState)
    b.add_node("agent", agent)
    b.add_node("tools", ToolNode(TOOLS))
    b.add_edge(START, "agent")
    b.add_conditional_edges("agent", tools_condition)  # -> "tools" if the last AI message has tool calls, else END
    b.add_edge("tools", "agent")  # the cycle that makes it ReAct
    return b.compile(checkpointer=InMemorySaver())


def trace(messages) -> list[str]:
    out = []
    for m in messages:
        if getattr(m, "tool_calls", None):
            out.append("call " + ", ".join(f"{tc['name']}({tc['args']})" for tc in m.tool_calls))
        elif m.type == "tool":
            out.append(f"tool {m.name} -> {m.content[:48]}")
        else:
            out.append(f"{m.type} {m.content[:80]}")
    return out


def run() -> list[str]:
    ask = {"messages": [{"role": "user", "content": "When does FW-HO-3381 renew and what would it cost with flood cover?"}]}
    cfg = {"configurable": {"thread_id": "policy-3381"}}
    hand_model, prebuilt_model = scripted(PLAYBOOK, name="by-hand"), scripted(PLAYBOOK, name="create_agent")
    hand = build_by_hand(hand_model)
    prebuilt = create_agent(prebuilt_model, TOOLS, checkpointer=InMemorySaver())
    a = trace(hand.invoke(ask, cfg)["messages"])
    b = trace(prebuilt.invoke(ask, cfg)["messages"])
    out = [f"{INSURANCE} - ReAct loop by hand vs create_agent", "", "hand-built graph edges:"]
    out += ["  " + line.strip() for line in hand.get_graph().draw_mermaid().splitlines() if "-->" in line or "-.->" in line]
    out += ["", "transcript (hand-built):"] + [f"  {x}" for x in a]
    out.append(f"same transcript from create_agent: {a == b}; model calls hand={hand_model.calls} create_agent={prebuilt_model.calls}")
    out.append(f"create_agent nodes: {[n for n in prebuilt.get_graph().nodes if not n.startswith('__')]}")
    return out
