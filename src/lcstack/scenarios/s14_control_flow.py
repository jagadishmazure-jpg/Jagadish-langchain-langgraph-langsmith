"""14 Control Flow: conditional edges, Command (route and update in one step), and Send (map-reduce).

Client: Kestrel Ridge Bank's payment-operations desk. Incoming payment exceptions are routed by type
and amount; an investigation node both records its finding and decides the next hop; month-end
statement packs are summarised in parallel, one Send per account, then combined.
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send

from lcstack.core.companies import BANKING
from lcstack.scenarios import Meta

META = Meta(14, "Control Flow", "add_conditional_edges with a router, Command(goto, update) with typed destinations, Send map-reduce, one routing method per node",
            f"{BANKING}: payment-exception routing and statement packs", "banking", "control-flow")  # fmt: skip


class Exception_(TypedDict, total=False):
    kind: str
    amount: float
    finding: str
    handled_by: Annotated[list[str], add]


def route(s: Exception_) -> Literal["sanctions_review", "investigate", "auto_repair"]:
    if s["kind"] == "sanctions_hit":
        return "sanctions_review"
    return "investigate" if s["amount"] >= 10_000 else "auto_repair"


def investigate(s: Exception_) -> Command[Literal["treasury", "auto_repair"]]:
    """Records a finding AND picks the next node: no static edge leaves this node (one routing method)."""
    if s["kind"] == "returned_wire":
        return Command(update={"finding": "beneficiary account closed", "handled_by": ["investigate"]}, goto="treasury")
    return Command(update={"finding": "format error only", "handled_by": ["investigate"]}, goto="auto_repair")


def build_router():
    b = StateGraph(Exception_)
    b.add_node("sanctions_review", lambda s: {"handled_by": ["sanctions_review"]})
    b.add_node("investigate", investigate)
    b.add_node("auto_repair", lambda s: {"handled_by": ["auto_repair"]})
    b.add_node("treasury", lambda s: {"handled_by": ["treasury"]})
    b.add_conditional_edges(START, route)
    for n in ("sanctions_review", "auto_repair", "treasury"):
        b.add_edge(n, END)
    return b.compile()


class Pack(TypedDict, total=False):
    accounts: list[dict]
    summaries: Annotated[list[str], add]
    report: str


def fan_out(s: Pack) -> list[Send]:
    return [Send("summarise", {"account": a}) for a in s["accounts"]]


def summarise(s: dict) -> dict:
    a = s["account"]
    flag = " LOW BALANCE" if a["closing"] < 500 else ""
    return {"summaries": [f"{a['id']}: {a['txns']} txns, closing {a['closing']:.2f}{flag}"]}


def combine(s: Pack) -> dict:
    return {"report": f"{len(s['summaries'])} statements; {sum('LOW' in x for x in s['summaries'])} flagged"}


def build_mapreduce():
    b = StateGraph(Pack)
    b.add_node("split", lambda s: {})
    b.add_node("summarise", summarise)
    b.add_node("combine", combine)
    b.add_edge(START, "split")
    b.add_conditional_edges("split", fan_out, ["summarise"])
    b.add_edge("summarise", "combine")
    b.add_edge("combine", END)
    return b.compile()


CASES = [
    {"kind": "sanctions_hit", "amount": 250.0},
    {"kind": "format_error", "amount": 900.0},
    {"kind": "returned_wire", "amount": 48_000.0},
    {"kind": "format_error", "amount": 15_500.0},
]


def run() -> list[str]:
    out = [f"{BANKING} - payment exception routing", ""]
    g = build_router()
    for c in CASES:
        r = g.invoke(c)
        out.append(f"  {c['kind']:<14} {c['amount']:>9.2f} -> path {r['handled_by']} finding={r.get('finding', '-')!r}")
    accounts = [{"id": f"KR-CHK-{i:03d}", "txns": 10 + 7 * i, "closing": 120.0 + 410 * i} for i in range(5)]
    mr = build_mapreduce().invoke({"accounts": accounts})
    out += ["", f"Send map-reduce over {len(accounts)} accounts (one summarise task each, same super-step):"]
    out += [f"  {x}" for x in sorted(mr["summaries"])]
    out.append(f"  combine -> {mr['report']}")
    return out
