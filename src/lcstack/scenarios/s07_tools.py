"""07 Tools: functions the model can call, schemas from docstrings, errors as text, MCP tools.

Client: Wrenfield Grocers' online order-refund agent. Refund rules (30-day window, no double refunds,
cap per order) live in the tools, not the prompt. Tool errors that the model can act on come back as
text; a real outage raises. Store inventory and loyalty points come from a separate team's MCP server.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from langchain.agents import create_agent
from langchain.tools import ToolException, tool
from langchain_core.messages import AIMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from lcstack.core.companies import RETAIL
from lcstack.core.scripted import Intent, Playbook, Turn, scripted
from lcstack.scenarios import Meta

META = Meta(7, "Tools", "@tool, docstring and type hints as schema, errors as text vs raising, ToolNode error handling, MCP via langchain-mcp-adapters",
            f"{RETAIL}: order-refund agent with an MCP inventory server", "retail", "tools")  # fmt: skip

ORDERS = {
    "ana@shopper.example": [
        {"order_id": "WG-1001", "total": 54.20, "age_days": 3, "refunded": False},
        {"order_id": "WG-0988", "total": 12.99, "age_days": 41, "refunded": False},
        {"order_id": "WG-0950", "total": 30.00, "age_days": 12, "refunded": True},
    ]
}
REFUNDS: list[str] = []
MCP_SERVER = Path(__file__).with_name("s07_mcp_server.py")


@tool
def search_orders(customer_email: str, max_results: int = 5) -> list[dict]:
    """Find a customer's most recent orders by email address.

    Call this before any refund so you refund an order that belongs to the customer."""
    return ORDERS.get(customer_email.lower(), [])[:max_results]


@tool
def refund_order(order_id: str, reason: str) -> str:
    """Refund one order in full. Only orders under 30 days old that were not already refunded qualify."""
    order = next((o for os_ in ORDERS.values() for o in os_ if o["order_id"] == order_id), None)
    if order is None:
        return f"ERROR: order {order_id} not found. Ask the customer to confirm the order number."
    if order["refunded"]:
        return f"ERROR: order {order_id} was already refunded. Do not refund it again."
    if order["age_days"] > 30:
        return f"ERROR: order {order_id} is {order['age_days']} days old, outside the 30-day window. Offer store credit instead."
    order["refunded"] = True
    REFUNDS.append(order_id)
    return f"Refunded {order_id}: {order['total']:.2f} back to the original card ({reason})."


@tool
def payments_gateway_health() -> str:
    """Check the payments gateway."""
    raise ToolException("payments gateway unreachable (simulated outage)")


def _email(t: Turn) -> str:
    import re

    m = re.search(r"[\w.]+@[\w.]+", t.last_human)
    return m.group(0) if m else ""


def _order(t: Turn) -> str:
    import re

    m = re.search(r"WG-\d+", t.last_human)
    return m.group(0) if m else ""


PLAYBOOK = Playbook(intents=[
    Intent("refund", r"refund", steps=[
        lambda t: ("search_orders", {"customer_email": _email(t), "max_results": 5}),
        lambda t: ("refund_order", {"order_id": _order(t), "reason": "customer request"}),
    ], answer=lambda t: t.results.get("refund_order", "").replace("ERROR: ", "I could not do that: ")),
    Intent("stock", r"stock|points", steps=[
        lambda t: [("store_inventory", {"sku": "SKU-OATS-1KG", "store": "Riverside"}), ("loyalty_points", {"customer_id": "C-118"})],
    ], answer=lambda t: f"{t.results.get('store_inventory')} {t.results.get('loyalty_points')}"),
])  # fmt: skip


GATEWAY_CALL = {"name": "payments_gateway_health", "args": {}, "id": "call_gw", "type": "tool_call"}


def tool_node_graph(*, handle_errors: bool):
    """A one-node graph around ToolNode (ToolNode needs the graph runtime to execute)."""
    b = StateGraph(MessagesState)
    b.add_node("tools", ToolNode([payments_gateway_health], handle_tool_errors=handle_errors))
    b.add_edge(START, "tools")
    return b.compile()


def reset() -> None:
    for os_ in ORDERS.values():
        for o in os_:
            o["refunded"] = o["order_id"] == "WG-0950"
    REFUNDS.clear()


async def mcp_demo() -> list[str]:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient({"inventory": {"transport": "stdio", "command": sys.executable, "args": [str(MCP_SERVER)]}})
    tools = await client.get_tools()
    agent = create_agent(scripted(PLAYBOOK, name="refund-agent"), tools)
    res = await agent.ainvoke({"messages": [{"role": "user", "content": "Is oats in stock at Riverside, and how many points do I have?"}]})
    return [f"MCP tools loaded over stdio: {sorted(t.name for t in tools)}", f"agent answer: {res['messages'][-1].content}"]


def run() -> list[str]:
    reset()
    out = [f"{RETAIL} - refund tools", ""]
    out.append(f"schema the model sees for refund_order: name={refund_order.name!r}")
    out.append(f"  description: {refund_order.description.splitlines()[0]}")
    out.append(f"  args: {refund_order.args}")
    agent = create_agent(scripted(PLAYBOOK, name="refund-agent"), [search_orders, refund_order])
    for ask in ["Please refund WG-1001 for ana@shopper.example", "Please refund WG-0988 for ana@shopper.example",
                "Please refund WG-0950 for ana@shopper.example", "Please refund WG-7777 for ana@shopper.example"]:  # fmt: skip
        res = agent.invoke({"messages": [{"role": "user", "content": ask}]})
        out.append(f"  {ask.split(' for ')[0]:<24} -> {res['messages'][-1].content}")
    out.append(f"refunds actually issued: {REFUNDS}")

    msg = tool_node_graph(handle_errors=True).invoke({"messages": [AIMessage("", tool_calls=[GATEWAY_CALL])]})["messages"][-1]
    out += ["", f"a raised ToolException, caught by ToolNode(handle_tool_errors=True): status={msg.status!r} content={msg.content!r}"]
    try:
        tool_node_graph(handle_errors=False).invoke({"messages": [AIMessage("", tool_calls=[GATEWAY_CALL])]})
        out.append("handle_tool_errors=False: no error (unexpected)")
    except ToolException as exc:
        out.append(f"handle_tool_errors=False: the run fails with ToolException({exc})")
    out += ["", *asyncio.run(mcp_demo())]
    return out
