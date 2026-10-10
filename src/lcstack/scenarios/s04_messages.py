"""04 Messages: the common currency between models, tools and graphs.

Client: Quillmere Home Loans stores borrower chats for audit. Transcripts arrive as plain dicts from
the web widget, contain an uploaded pay-stub image, and include tool calls to the rate-lock system.
The scenario normalises them into message classes, checks that every ToolMessage answers a real tool
call, trims long histories to a budget and round-trips them to JSON for the audit store.
"""

from __future__ import annotations

import json

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    convert_to_messages,
    filter_messages,
    messages_from_dict,
    messages_to_dict,
    trim_messages,
)

from lcstack.core.companies import MORTGAGE
from lcstack.core.scripted import count_tokens, text_of
from lcstack.scenarios import Meta

META = Meta(4, "Messages", "System/Human/AI/Tool messages, dict form, multimodal blocks, tool_call_id pairing, trimming, serialisation",
            f"{MORTGAGE}: borrower chat transcripts for audit", "mortgage", "messages")  # fmt: skip

WIDGET_TRANSCRIPT = [
    {"role": "system", "content": "You are Quillmere's loan assistant. Never quote a rate you did not look up."},
    {"role": "user", "content": "Hi, I locked my rate last month. When does the lock expire? Loan QH-4471."},
]


def build_transcript() -> list[BaseMessage]:
    msgs = convert_to_messages(WIDGET_TRANSCRIPT)
    msgs.append(AIMessage(content="", tool_calls=[{"name": "get_rate_lock", "args": {"loan_id": "QH-4471"}, "id": "call_lock_1"}]))
    msgs.append(
        ToolMessage(content='{"loan_id": "QH-4471", "rate": 6.125, "expires": "in 9 days"}', tool_call_id="call_lock_1", name="get_rate_lock")
    )
    msgs.append(AIMessage(content="Your 6.125% lock on QH-4471 expires in 9 days.",
                          usage_metadata={"input_tokens": 61, "output_tokens": 14, "total_tokens": 75}))  # fmt: skip
    msgs.append(HumanMessage(content=[
        {"type": "text", "text": "Here is my latest pay stub, is it enough for underwriting?"},
        {"type": "image", "url": "https://files.example/quillmere/paystub-QH-4471.png"},
    ]))  # fmt: skip
    return msgs


def unanswered_or_orphaned(msgs: list[BaseMessage]) -> dict[str, list[str]]:
    """Every tool call must be answered by a ToolMessage with the same id, and vice versa."""
    calls = {tc["id"] for m in msgs if isinstance(m, AIMessage) for tc in m.tool_calls}
    answers = {m.tool_call_id for m in msgs if isinstance(m, ToolMessage)}
    return {"unanswered_calls": sorted(calls - answers), "orphan_tool_messages": sorted(answers - calls)}


def token_counter(msgs: list[BaseMessage]) -> int:
    return sum(count_tokens(text_of(m)) for m in msgs)


def run() -> list[str]:
    msgs = build_transcript()
    out = [f"{MORTGAGE} - borrower transcript as LangChain messages", ""]
    for m in msgs:
        extra = ""
        if isinstance(m, AIMessage) and m.tool_calls:
            extra = f" tool_calls={[(tc['name'], tc['args']) for tc in m.tool_calls]}"
        if isinstance(m, ToolMessage):
            extra = f" tool_call_id={m.tool_call_id}"
        if isinstance(m.content, list):
            extra = f" blocks={[b['type'] for b in m.content]}"
        body = text_of(m)
        out.append(f"{type(m).__name__:<13} {body[:60]!r}{extra}")
    out += ["", f"pairing check: {unanswered_or_orphaned(msgs)}"]
    broken = [*msgs[:2], msgs[2]]  # an AI tool call with no ToolMessage after it
    out.append(f"pairing check on a truncated copy: {unanswered_or_orphaned(broken)}")
    out.append(f"usage on the final answer: {msgs[4].usage_metadata}")
    trimmed = trim_messages(msgs, max_tokens=60, token_counter=token_counter, strategy="last", include_system=True, start_on="human")
    out.append(f"trim to 60 tokens, keep system, start on a human turn: {[type(m).__name__ for m in trimmed]}")
    humans = filter_messages(msgs, include_types=[HumanMessage, SystemMessage])
    out.append(f"filter to system + human: {len(humans)} messages")
    blob = json.dumps(messages_to_dict(msgs))
    back = messages_from_dict(json.loads(blob))
    out.append(f"JSON round trip for the audit store: {len(blob)} bytes, equal after reload: {back == msgs}")
    return out
