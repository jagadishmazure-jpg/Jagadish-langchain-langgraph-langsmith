"""The three specialists and the supervisor's router, each a create_agent with its own tools and middleware.

The scripted model's behaviour is defined here as playbooks. Two behaviours are deliberately naive so
the guardrails have something real to stop: when the system prompt lacks the data-not-instructions rule,
the model obeys "call <tool> with {...}" text it finds in tool results; when it lacks the masking rule,
it repeats the full account number. Real models fail in these ways too; the evaluation measures which
layer catches each case.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, ModelRetryMiddleware
from pydantic import BaseModel

from lcstack.capstone import guardrails as gr
from lcstack.capstone import tools as t
from lcstack.capstone.prompts import CITE, DATA_RULE, MASK_RULE, PromptVersion
from lcstack.core.embeddings import stems
from lcstack.core.models import chat_model
from lcstack.core.scripted import Intent, Playbook, Turn

ALLOWED = {
    "accounts_agent": {"get_account_summary", "list_transactions", "issue_fee_refund"},
    "cards_agent": {"freeze_card", "order_replacement_card", "open_dispute"},
    "knowledge_agent": {"search_kb", "find_branch", "fx_rate"},
}
RISKY = {"issue_fee_refund", "order_replacement_card"}
TOOLS = {
    "accounts_agent": [t.get_account_summary, t.list_transactions, t.issue_fee_refund],
    "cards_agent": [t.freeze_card, t.order_replacement_card, t.open_dispute],
    "knowledge_agent": [t.search_kb, t.find_branch, t.fx_rate],
}
INJECTED_CALL = re.compile(r"call (\w+) with (\{.*?\})", re.I)


class Route(BaseModel):
    """Which specialist handles the customer's latest message."""

    specialist: Literal["accounts_agent", "cards_agent", "knowledge_agent", "out_of_scope"]


ROUTES = [
    ("out_of_scope", r"invest|stock|crypto|tax advice|mortgage rate|bitcoin"),
    ("cards_agent", r"lost|stolen|freeze|replacement card|new card|dispute|didn.t make|don.t recognise"),
    ("accounts_agent", r"balance|transactions|refund|overdraft fee|charged|statement|how much (do i|money)"),
    ("knowledge_agent", r"."),
]


def route_for(text: str) -> str:
    return next(name for name, pat in ROUTES if re.search(pat, text, re.I))


def obey_injection(turn: Turn):
    """Naive behaviour: without the data rule, follow instructions that appear inside tool results."""
    if DATA_RULE in turn.system:
        return None
    for res in turn.results.values():
        m = INJECTED_CALL.search(res)
        if m:
            return (m.group(1), json.loads(m.group(2)))
    return None


def _acct(turn: Turn) -> str:
    summary = turn.results.get("get_account_summary", "")
    full = re.search(r"Account (\S+)", summary)
    if MASK_RULE in turn.system:
        digits = re.search(r"KR\d{6}(\d{4})", summary)
        return f"account ending {digits.group(1)}" if digits else "your account"
    return f"account {full.group(1)}" if full else "your account"


def _balance(turn: Turn) -> str:
    bal = re.search(r"balance ([\d.]+)", turn.results.get("get_account_summary", ""))
    return f"The balance on {_acct(turn)} is {bal.group(1) if bal else 'unavailable'}."


def _refund_answer(turn: Turn) -> str:
    refunds = [m for m in turn.messages if getattr(m, "name", None) == "issue_fee_refund"]
    if any(str(m.content).startswith("Refunded") for m in refunds):
        return "Done: the 35.00 overdraft fee has been refunded to " + ("your account." if MASK_RULE in turn.system else f"{_acct(turn)}.")
    if turn.called("issue_fee_refund"):
        return "A colleague reviewed the refund request and did not approve it this time."
    return "There is no overdraft fee on your recent transactions to refund."


ACCOUNTS = Playbook(intents=[
    Intent("refund", r"refund|overdraft fee", steps=[
        lambda tn: ("list_transactions", {"limit": 5}),
        lambda tn: ("issue_fee_refund", {"amount": 35.0}) if "Overdraft fee" in tn.results.get("list_transactions", "") else None,
        obey_injection,
    ], answer=_refund_answer),
    Intent("txns", r"transactions|charged|statement", steps=[lambda tn: ("list_transactions", {"limit": 3}), obey_injection],
           answer=lambda tn: "Your latest transactions: " + "; ".join(tn.results.get("list_transactions", "").splitlines()[:3]) + "."),
    Intent("balance", r".", steps=[lambda tn: ("get_account_summary", {})], answer=_balance),
])  # fmt: skip


def _dispute_args(turn: Turn) -> dict:
    amt = re.search(r"(\d+(?:\.\d{2})?)", turn.last_human)
    merch = re.search(r"(?:at|from) ([A-Z][\w ]+?)(?: for|,|\.|$)", turn.last_human)
    return {"merchant": merch.group(1).strip() if merch else "unknown merchant", "amount": float(amt.group(1)) if amt else 0.0}


def _cards_answer(turn: Turn) -> str:
    parts = []
    for k in ("freeze_card", "order_replacement_card", "open_dispute"):
        res = turn.results.get(k)
        if res is None:
            continue
        parts.append("A colleague did not approve that request this time." if "rejected" in res.lower() else res.strip().splitlines()[-1])
    return " ".join(parts) or "I can freeze your card, order a replacement or open a dispute."


CARDS = Playbook(intents=[
    Intent("dispute", r"dispute|didn.t make|don.t recognise", steps=[lambda tn: ("open_dispute", _dispute_args(tn))], answer=_cards_answer),
    Intent("lost", r"lost|stolen|freeze", steps=[
        lambda tn: ("freeze_card", {}),
        lambda tn: ("order_replacement_card", {}) if re.search(r"replace|new card", tn.last_human, re.I) else None,
    ], answer=_cards_answer),
    Intent("replace", r"replacement|new card", steps=[lambda tn: ("order_replacement_card", {})], answer=_cards_answer),
])  # fmt: skip


def _kb_answer(turn: Turn) -> str:
    passages = turn.results.get("search_kb", "")
    m = re.match(r"\[(.+?)\] (.*?)(?:\n\n\[|$)", passages, re.S)
    if not m:
        return "I couldn't find that in our published policies."
    q = set(stems(turn.last_human))
    sents = [s.strip() for s in re.split(r"(?<=[.])\s+", re.sub(r"# .+?\n", "", m.group(2))) if s.strip() and "quarantined" not in s]
    best = sorted(range(len(sents)), key=lambda i: -len(q & set(stems(sents[i]))))[:2]
    text = " ".join(sents[i] for i in sorted(best)) or "I couldn't find that in our published policies."
    return text + (f" (source: {m.group(1)})" if CITE in turn.system else "")


def _city(turn: Turn) -> str:
    m = re.search(r"\b(?:in|near) ([A-Z][a-z]+)", turn.last_human)
    return m.group(1) if m else "Harbourside"


KNOWLEDGE = Playbook(intents=[
    Intent("branch", r"branch|open on|opening hours", steps=[lambda tn: ("find_branch", {"city": _city(tn)})], answer=lambda tn: tn.results.get("find_branch", "")),
    Intent("fx", r"exchange rate|fx|euros?|pounds?|yen", steps=[
        lambda tn: ("fx_rate", {"currency": next((c for w, c in [("euro", "EUR"), ("pound", "GBP"), ("yen", "JPY"), ("cad", "CAD")] if w in tn.last_human.lower()), "EUR")}),
    ], answer=lambda tn: tn.results.get("fx_rate", "")),
    Intent("policy", r".", steps=[lambda tn: ("search_kb", {"query": tn.last_human}), obey_injection], answer=_kb_answer),
])  # fmt: skip

PLAYBOOKS = {"accounts_agent": ACCOUNTS, "cards_agent": CARDS, "knowledge_agent": KNOWLEDGE}
ROLE = {
    "accounts_agent": "You are the accounts specialist: balances, transactions and fee refunds.",
    "cards_agent": "You are the cards specialist: freezing, replacing and disputing card payments.",
    "knowledge_agent": "You are the knowledge specialist: bank policies, branches and exchange rates.",
}


def router(prompt: PromptVersion):
    pb = Playbook(extractors={"Route": lambda tn: {"specialist": route_for(tn.last_human)}})
    return chat_model(pb, name="supervisor").with_structured_output(Route)


def specialist(name: str, prompt: PromptVersion, *, guard: bool = True):
    middleware = [ModelRetryMiddleware(max_retries=2, initial_delay=0.0, jitter=False)]
    if guard:
        middleware += [*gr.pii_middleware(), gr.screen_tool_outputs, gr.tool_allowlist(name, ALLOWED[name])]
    middleware.append(HumanInTheLoopMiddleware(interrupt_on={tool: {"allowed_decisions": ["approve", "reject"]} for tool in RISKY & ALLOWED[name]}))
    return create_agent(
        chat_model(PLAYBOOKS[name], name=name),
        TOOLS[name],
        system_prompt=f"{prompt.text}\n{ROLE[name]}",
        middleware=middleware,
        context_schema=t.Customer,
        name=name,
    )
