"""18 Streaming: show progress, not a spinner.

Client: Wrenfield Grocers' order-tracking assistant in the mobile app. The UI shows "checking your
order..." while tools run (custom events from inside the tool), streams the answer token by token
(messages), and the support console records node-level updates. One run is streamed with several modes
at once and every event is counted.
"""

from __future__ import annotations

from collections import Counter

from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer

from lcstack.core.companies import RETAIL
from lcstack.core.scripted import Intent, Playbook, scripted
from lcstack.scenarios import Meta

META = Meta(18, "Streaming", "stream_mode values / updates / messages / custom / debug, several modes at once, get_stream_writer from a tool, astream",
            f"{RETAIL}: order-tracking assistant in the mobile app", "retail", "streaming")  # fmt: skip


@tool
def track_order(order_id: str) -> str:
    """Track a grocery delivery order."""
    writer = get_stream_writer()
    writer({"progress": "contacting the store"})
    writer({"progress": "locating the driver"})
    return f"{order_id}: out for delivery, driver 2 stops away, ETA 18:40"


PLAYBOOK = Playbook(intents=[Intent("track", r"where|track", steps=[lambda t: ("track_order", {"order_id": "WG-2204"})],
                                    answer=lambda t: f"Good news: your order is out for delivery and should arrive around {t.results['track_order'].split('ETA ')[1]}.")])  # fmt: skip


def build():
    return create_agent(scripted(PLAYBOOK, name="tracker"), [track_order], checkpointer=InMemorySaver())


def run() -> list[str]:
    agent = build()
    ask = {"messages": [{"role": "user", "content": "Where is my order WG-2204?"}]}
    out = [f"{RETAIL} - streaming one run with five modes", ""]
    counts: Counter[str] = Counter()
    tokens, custom, updates = [], [], []
    for mode, chunk in agent.stream(ask, {"configurable": {"thread_id": "t-1"}}, stream_mode=["values", "updates", "messages", "custom", "debug"]):
        counts[mode] += 1
        if mode == "messages":
            msg, meta = chunk
            if msg.type == "AIMessageChunk" and msg.content:
                tokens.append((msg.content, meta["langgraph_node"]))
        elif mode == "custom":
            custom.append(chunk["progress"])
        elif mode == "updates":
            updates.append(next(iter(chunk)))
    out.append(f"events per mode: {dict(sorted(counts.items()))}")
    out.append(f"custom (from inside the tool): {custom}")
    out.append(f"updates (node order): {updates}")
    out.append(f"messages: {len(tokens)} token chunks from node {sorted({n for _, n in tokens})}: {''.join(t for t, _ in tokens)!r}")
    v = list(build().stream(ask, {"configurable": {"thread_id": "t-2"}}, stream_mode="values"))
    out.append(f"values: {len(v)} full-state snapshots; message count grows {[len(s['messages']) for s in v]}")
    return out
