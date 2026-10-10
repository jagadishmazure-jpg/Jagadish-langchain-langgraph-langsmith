"""08 create_agent: a production agent in a dozen lines, with memory per thread and per-run context.

Client: Wrenfield Grocers' billing-ticket agent for store managers. The agent must remember the ticket
conversation (checkpointer + thread_id), know which store and user it is acting for without trusting
the chat text (context_schema read by tools), and return a typed ticket outcome (response_format).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel

from lcstack.core.companies import RETAIL
from lcstack.core.persist import memory_saver
from lcstack.core.scripted import Intent, Playbook, Turn, scripted
from lcstack.scenarios import Meta

META = Meta(8, "create_agent", "create_agent with tools, system_prompt, checkpointer, context_schema (ToolRuntime) and response_format",
            f"{RETAIL}: billing-ticket agent for store managers", "retail", "create-agent")  # fmt: skip

INVOICES = {("store-12", "INV-5521"): {"amount": 1840.00, "status": "overdue"}, ("store-40", "INV-7710"): {"amount": 220.00, "status": "paid"}}


@dataclass
class StoreCtx:
    store_id: str
    user_id: str
    role: str = "manager"


class TicketOutcome(BaseModel):
    invoice_id: str
    status: Literal["paid", "overdue", "not_found"]
    action: Literal["none", "payment_plan_offered", "escalated"]


@tool
def get_invoice(invoice_id: str, runtime: ToolRuntime[StoreCtx]) -> str:
    """Look up an invoice for the caller's own store."""
    inv = INVOICES.get((runtime.context.store_id, invoice_id))
    if inv is None:
        return f"not_found: {invoice_id} is not an invoice of {runtime.context.store_id}"
    return f"{invoice_id} for {runtime.context.store_id}: {inv['amount']:.2f}, {inv['status']}"


def _inv(t: Turn) -> str:
    for m in reversed(t.messages):  # the invoice may have been named in an earlier turn of the same thread
        found = re.search(r"INV-\d+", str(m.content))
        if found:
            return found.group(0)
    return ""


def _outcome(t: Turn) -> dict:
    res = next((str(m.content) for m in reversed(t.messages) if getattr(m, "name", None) == "get_invoice"), "")
    status = "not_found" if res.startswith("not_found") else "overdue" if "overdue" in res else "paid"
    action = "payment_plan_offered" if status == "overdue" and re.search(r"plan|instal", t.last_human, re.I) else "none"
    return {"invoice_id": _inv(t), "status": status, "action": action}


PLAYBOOK = Playbook(
    intents=[
        Intent("lookup", r"INV-\d+", steps=[lambda t: ("get_invoice", {"invoice_id": _inv(t)})]),
        Intent("followup", r"plan|instal", answer="A 3-month payment plan has been offered."),
    ],
    extractors={"TicketOutcome": _outcome},
)


def build(checkpointer=None):
    model = scripted(PLAYBOOK, name="billing-agent")
    agent = create_agent(
        model=model,
        tools=[get_invoice],
        system_prompt="You resolve store billing tickets. Only discuss the caller's own store.",
        context_schema=StoreCtx,
        response_format=TicketOutcome,
        checkpointer=checkpointer or memory_saver(TicketOutcome),
    )
    return agent, model


def run() -> list[str]:
    agent, model = build()
    out = [f"{RETAIL} - billing-ticket agent built with create_agent", ""]
    cfg = {"configurable": {"thread_id": "ticket-store12-001"}}
    ctx = StoreCtx(store_id="store-12", user_id="mgr-ellis")
    r1 = agent.invoke({"messages": [{"role": "user", "content": "What's the status of INV-5521?"}]}, cfg, context=ctx)
    out.append(f"turn 1 structured_response: {r1['structured_response'].model_dump()}")
    r2 = agent.invoke({"messages": [{"role": "user", "content": "Can we set up a payment plan for it?"}]}, cfg, context=ctx)
    out.append(f"turn 2 (same thread, invoice id not repeated): {r2['structured_response'].model_dump()}")
    out.append(f"messages stored on the thread: {len(agent.get_state(cfg).values['messages'])}")
    r3 = agent.invoke(
        {"messages": [{"role": "user", "content": "What's the status of INV-7710?"}]},
        {"configurable": {"thread_id": "ticket-store12-002"}},
        context=ctx,
    )
    out.append(f"store-12 asking about store-40's INV-7710 -> {r3['structured_response'].model_dump()} (context, not chat text, scopes the tool)")
    r4 = agent.invoke(
        {"messages": [{"role": "user", "content": "Can we set up a payment plan for it?"}]},
        {"configurable": {"thread_id": "ticket-store12-003"}},
        context=ctx,
    )
    out.append(f"new thread_id, follow-up only -> invoice_id={r4['structured_response'].invoice_id!r} (no memory on a new thread)")
    out.append(f"model calls: {model.calls}")
    return out
