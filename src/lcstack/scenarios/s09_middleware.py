"""09 Middleware: customise the agent loop without forking it.

Client: Kestrel Ridge Bank's card-dispute agent. Compliance asked for: card numbers and emails never
reach the model; provisional credits need a human; flaky model and fraud-score calls are retried; a
runaway conversation is cut off; every tool call is audit-logged; premium customers get a different
prompt; long histories are summarised. Each requirement is one middleware.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentState,
    HumanInTheLoopMiddleware,
    ModelRequest,
    ModelRetryMiddleware,
    PIIMiddleware,
    SummarizationMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
    before_model,
    dynamic_prompt,
    wrap_tool_call,
)
from langchain.tools import tool
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime
from langgraph.types import Command

from lcstack.core.companies import BANKING
from lcstack.core.scripted import Intent, Playbook, Turn, scripted, text_of
from lcstack.scenarios import Meta

META = Meta(9, "Middleware", "before_model with jump_to, HumanInTheLoop, PII, Model/ToolRetry, ToolCallLimit, wrap_tool_call, dynamic_prompt, Summarization",
            f"{BANKING}: card-dispute agent under compliance controls", "banking", "middleware")  # fmt: skip

AUDIT: list[str] = []
FRAUD_SCORE_CALLS = [0]


@dataclass
class Customer:
    customer_id: str
    tier: str = "standard"


@tool
def lookup_transaction(txn_id: str) -> str:
    """Look up one card transaction by id."""
    return f"{txn_id}: 89.00 at a merchant abroad, card present=False"


@tool
def fraud_score(txn_id: str) -> str:
    """Score a transaction for fraud (0-100). The scoring service is occasionally slow."""
    FRAUD_SCORE_CALLS[0] += 1
    if FRAUD_SCORE_CALLS[0] == 1:
        raise TimeoutError("fraud scoring service timed out (simulated)")
    return f"{txn_id}: fraud score 91"


@tool
def issue_provisional_credit(account: str, amount: float) -> str:
    """Credit the customer's account while the dispute is investigated. Requires approval."""
    return f"Provisional credit of {amount:.2f} posted to {account}."


def _txn(t: Turn) -> str:
    m = re.search(r"TX-\d+", t.last_human)
    return m.group(0) if m else "TX-0"


def _answer(t: Turn) -> str:
    credit = t.results.get("issue_provisional_credit", "no credit issued").strip().splitlines()[-1]
    return f"Dispute opened. {t.results.get('fraud_score', '')}. {credit}"


PLAYBOOK = Playbook(intents=[
    Intent("dispute", r"dispute", steps=[
        lambda t: ("lookup_transaction", {"txn_id": _txn(t)}),
        lambda t: ("fraud_score", {"txn_id": _txn(t)}),
        lambda t: ("issue_provisional_credit", {"account": "ACC-ending-0042", "amount": 89.0}),
    ], answer=_answer),
    # a model that keeps checking until the middleware tells it to stop
    Intent("loop", r"check again", steps=[lambda t: None if "limit exceeded" in t.results.get("lookup_transaction", "")
                                          else ("lookup_transaction", {"txn_id": f"TX-{len(t.calls)}"})], answer="Stopped: lookup limit reached."),
    Intent("chat", r".", answer=lambda t: f"Noted ({len(t.messages)} messages in context)."),
])  # fmt: skip


@before_model(can_jump_to=["end"])
def cap_turns(state: AgentState, runtime: Runtime) -> dict | None:
    """Stop a conversation that has run away (cheap guard against loops and abuse)."""
    if len(state["messages"]) > 40:
        return {"messages": [AIMessage("This conversation is too long; a colleague will follow up.")], "jump_to": "end"}
    return None


@wrap_tool_call
def audit_log(request, handler):
    """Write every tool call and its outcome to the audit trail."""
    result = handler(request)
    status = getattr(result, "status", "success")
    AUDIT.append(f"{request.tool_call['name']}({request.tool_call['args']}) -> {status}")
    return result


@dynamic_prompt
def tiered_prompt(request: ModelRequest) -> str:
    tier = request.runtime.context.tier if request.runtime.context else "standard"
    base = "You handle card disputes for Kestrel Ridge Bank."
    return base + (" Premium customer: offer a call-back within 1 hour." if tier == "premium" else "")


def account_number_detector(text: str) -> list[dict]:
    return [{"type": "account_number", "value": m.group(0), "start": m.start(), "end": m.end()} for m in re.finditer(r"\bKR\d{10}\b", text)]


def build(model, *, extra=()):
    return create_agent(
        model,
        [lookup_transaction, fraud_score, issue_provisional_credit],
        context_schema=Customer,
        checkpointer=InMemorySaver(),
        middleware=[
            cap_turns,
            tiered_prompt,
            PIIMiddleware("email", strategy="redact", apply_to_input=True),
            PIIMiddleware("credit_card", strategy="mask", apply_to_input=True),
            PIIMiddleware("account_number", detector=account_number_detector, strategy="hash", apply_to_input=True),
            ModelRetryMiddleware(max_retries=2, initial_delay=0.0, jitter=False),
            ToolRetryMiddleware(max_retries=2, tools=["fraud_score"], initial_delay=0.0, jitter=False),
            ToolCallLimitMiddleware(tool_name="lookup_transaction", run_limit=3),
            HumanInTheLoopMiddleware(interrupt_on={"issue_provisional_credit": {"allowed_decisions": ["approve", "edit", "reject"]}}),
            audit_log,
            *extra,
        ],
    )


def run() -> list[str]:
    AUDIT.clear()
    FRAUD_SCORE_CALLS[0] = 0
    model = scripted(PLAYBOOK, name="dispute-agent", fail_times=1)
    agent = build(model)
    cfg = {"configurable": {"thread_id": "dispute-7731"}}
    ctx = Customer("C-7731", tier="premium")
    ask = "I want to dispute TX-55120. Card 4111 1111 1111 1111, email jo@customer.example, account KR0012345678."
    first = agent.invoke({"messages": [{"role": "user", "content": ask}]}, cfg, context=ctx)
    out = [f"{BANKING} - dispute agent with ten middleware", ""]
    seen = model.inputs[-1]
    out.append(f"system prompt the model got (dynamic_prompt, premium): {text_of(next(m for m in seen if isinstance(m, SystemMessage)))!r}")
    out.append(f"user text the model got (PII middleware): {text_of(next(m for m in seen if isinstance(m, HumanMessage)))!r}")
    out.append(f"ModelRetryMiddleware: first model call timed out, run continued (model calls so far: {model.calls})")
    out.append(f"ToolRetryMiddleware: fraud_score attempts = {FRAUD_SCORE_CALLS[0]} (1 timeout + 1 success)")
    pending = first["__interrupt__"][0].value["action_requests"][0]
    out.append(f"HumanInTheLoop paused before: {pending['name']}({pending['args']})")
    final = agent.invoke(
        Command(
            resume={
                "decisions": [
                    {"type": "edit", "edited_action": {"name": "issue_provisional_credit", "args": {"account": "ACC-ending-0042", "amount": 45.0}}}
                ]
            }
        ),
        cfg,
        context=ctx,
    )
    out.append(f"reviewer edited the amount to 45.00 -> {final['messages'][-1].content}")
    out += ["", "audit trail (wrap_tool_call):"] + [f"  {a}" for a in AUDIT]

    loop_model = scripted(PLAYBOOK, name="loop-agent")
    looped = build(loop_model).invoke(
        {"messages": [{"role": "user", "content": "check again and again"}]}, {"configurable": {"thread_id": "loop"}}, context=Customer("C-1")
    )
    blocked = [m for m in looped["messages"] if isinstance(m, ToolMessage) and m.status == "error"]
    ok_calls = [m for m in looped["messages"] if isinstance(m, ToolMessage) and m.status != "error"]
    out += [
        "",
        f"ToolCallLimitMiddleware(run_limit=3): {len(ok_calls)} lookups ran, {len(blocked)} blocked; last: {blocked[-1].content[:70] if blocked else '-'}",
    ]

    def history(n: int) -> list:
        return [HumanMessage(f"Earlier note {i} about the dispute") if i % 2 == 0 else AIMessage(f"Ack {i}") for i in range(n)]

    long_hist = history(30)
    summariser = scripted(Playbook(fallback="Summary: customer disputes TX-55120 (89.00 abroad); credit pending review."), name="summariser")
    chat_model = scripted(PLAYBOOK, name="chat")
    summarised = create_agent(chat_model, [], middleware=[SummarizationMiddleware(summariser, trigger=("messages", 20), keep=("messages", 6))])
    summarised.invoke({"messages": [*long_hist, HumanMessage("Any update?")]})
    got = chat_model.inputs[-1]
    out.append(f"SummarizationMiddleware: 31 messages in, model saw {len(got)}; first: {text_of(got[0])[:60]!r}")
    capped = build(scripted(PLAYBOOK, name="cap")).invoke(
        {"messages": [*history(60), HumanMessage("hello")]}, {"configurable": {"thread_id": "cap"}}, context=Customer("C-2")
    )
    out.append(f"cap_turns (before_model, jump_to end) on a 61-message thread: {capped['messages'][-1].content!r}")
    return out
