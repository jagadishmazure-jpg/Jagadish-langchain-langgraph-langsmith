"""15 Persistence: threads, checkpoints, inspection, editing, time travel; memory, SQLite and Postgres.

Client: Kestrel Ridge Bank's dispute workflow. A dispute case runs over days: intake, evidence from the
merchant, then a decision. The process restarts between steps, auditors need every intermediate state,
and an operations lead occasionally needs to correct a field and replay from an earlier step.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from operator import add
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from lcstack.core.companies import BANKING
from lcstack.scenarios import Meta

META = Meta(15, "Persistence", "thread_id, InMemorySaver / SqliteSaver / PostgresSaver, get_state, get_state_history, update_state, replay and fork from a checkpoint",
            f"{BANKING}: multi-day dispute case workflow", "banking", "persistence")  # fmt: skip


class Case(TypedDict, total=False):
    case_id: str
    amount: float
    merchant_response: str
    decision: str
    log: Annotated[list[str], add]


def intake(s: Case) -> dict:
    return {"log": [f"intake {s['case_id']} for {s['amount']:.2f}"]}


def evidence(s: Case) -> dict:
    return {"merchant_response": s.get("merchant_response") or "no response in 10 days", "log": ["evidence requested"]}


def decide(s: Case) -> dict:
    won = s["merchant_response"] != "proof of delivery supplied"
    return {"decision": "refund customer" if won else "decline dispute", "log": ["decided"]}


def builder() -> StateGraph:
    b = StateGraph(Case)
    b.add_node("intake", intake)
    b.add_node("evidence", evidence)
    b.add_node("decide", decide)
    b.add_edge(START, "intake")
    b.add_edge("intake", "evidence")
    b.add_edge("evidence", "decide")
    b.add_edge("decide", END)
    return b


def sqlite_restart_demo(path: Path) -> list[str]:
    """Run the first step, 'restart' (new connection and new graph object), and continue from disk."""
    with sqlite3.connect(path, check_same_thread=False) as conn:
        g1 = builder().compile(checkpointer=SqliteSaver(conn), interrupt_after=["intake"])
        g1.invoke({"case_id": "D-4410", "amount": 312.40}, {"configurable": {"thread_id": "D-4410"}})
    with sqlite3.connect(path, check_same_thread=False) as conn:
        g2 = builder().compile(checkpointer=SqliteSaver(conn))
        cfg = {"configurable": {"thread_id": "D-4410"}}
        before = g2.get_state(cfg)
        final = g2.invoke(None, cfg)
    return [
        f"  after restart the saved thread was waiting at next={before.next}",
        f"  resumed to the end: decision={final['decision']!r}, log={final['log']}",
    ]


def postgres_demo(url: str) -> list[str]:
    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(url) as saver:
        saver.setup()  # creates the checkpoint tables once (idempotent)
        g = builder().compile(checkpointer=saver)
        cfg = {"configurable": {"thread_id": "D-PG-1"}}
        g.invoke({"case_id": "D-PG-1", "amount": 75.0}, cfg)
        n = len(list(g.get_state_history(cfg)))
        return [f"  PostgresSaver: decision={g.get_state(cfg).values['decision']!r}, checkpoints={n}"]


def run() -> list[str]:
    out = [f"{BANKING} - dispute case persistence", ""]
    g = builder().compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "D-4409"}}
    g.invoke({"case_id": "D-4409", "amount": 129.99}, cfg)
    snap = g.get_state(cfg)
    out.append(f"InMemorySaver: values.decision={snap.values['decision']!r} next={snap.next}")
    history = list(g.get_state_history(cfg))
    out.append(f"history: {len(history)} checkpoints, newest first: {[h.metadata['step'] for h in history]}")
    after_evidence = next(h for h in history if h.next == ("decide",))
    out.append(f"checkpoint before 'decide': merchant_response={after_evidence.values['merchant_response']!r}")

    fork_cfg = g.update_state(after_evidence.config, {"merchant_response": "proof of delivery supplied"})
    forked = g.invoke(None, fork_cfg)
    out.append(f"fork: update_state on that checkpoint, then invoke(None) -> decision={forked['decision']!r}")
    replayed = g.invoke(None, after_evidence.config)
    out.append(f"replay the original checkpoint unchanged -> decision={replayed['decision']!r}")
    out.append(f"latest state on the thread is now the replay: {g.get_state(cfg).values['decision']!r}")
    other = g.get_state({"configurable": {"thread_id": "D-9999"}})
    out.append(f"a thread that never ran has empty values: {other.values}")

    out += ["", "SqliteSaver (file on disk, survives a restart):"]
    with tempfile.TemporaryDirectory() as d:
        out += sqlite_restart_demo(Path(d) / "disputes.sqlite")
    url = os.getenv("DATABASE_URL")
    out += ["", "PostgresSaver (production):"]
    out += postgres_demo(url) if url else ["  skipped here: set DATABASE_URL (CI runs it against a postgres:17 service container)"]
    return out
