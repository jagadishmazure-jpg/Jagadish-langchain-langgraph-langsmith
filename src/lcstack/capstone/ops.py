"""Operations around the support desk: tracing, streaming, HITL walkthrough, monitoring and online feedback.

Monitoring reads the offline LangSmith recorder (the same run payloads LangSmith would hold) after a
full evaluation pass and computes the signals an on-call engineer would chart: model and tool calls per
conversation, tool errors, human-approval rate, guard interventions and token usage (simulated counts
from the scripted model). Alert rules are thresholds in ``ALERTS``; with LangSmith these become
dashboard charts and automation rules on the project.

Online feedback: a thumbs score per conversation, recorded locally and, when LangSmith is enabled,
sent with ``Client.create_feedback(run_id, key="user_score", ...)`` against the root run.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from dataclasses import dataclass, field

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from langsmith.run_helpers import tracing_context

from lcstack.capstone import evals
from lcstack.capstone import tools as t
from lcstack.capstone.graph import build
from lcstack.capstone.prompts import all_versions, get_prompt, registry
from lcstack.core.tracing import OfflineLangSmithClient, deep_mask, langsmith_enabled

ALERTS = {"guard_events_per_100": 30.0, "tool_error_rate": 0.10, "approval_rate": 0.25, "model_calls_per_conversation": 6.0}


def _masked_client() -> OfflineLangSmithClient:
    from lcstack.capstone.guardrails import ACCOUNT

    return OfflineLangSmithClient(hide_inputs=deep_mask(ACCOUNT, "KR**********"), hide_outputs=deep_mask(ACCOUNT, "KR**********"))


def trace_demo() -> list[str]:
    client = _masked_client()
    with tracing_context(
        enabled=True, client=client, project_name="kestrel-support-desk", tags=["capstone"], metadata={"prompt_version": get_prompt().version}
    ):
        out = asyncio.run(evals.run_case("Please refund the overdraft fee", "C-100", reference={"reviewer": "approve"}))
    lines = [f"tracing mode: {'LangSmith' if langsmith_enabled() else 'offline recorder (set LANGSMITH_TRACING=true and LANGSMITH_API_KEY to send)'}",
             f"answer: {out['answer']}", f"human reviews: {out['reviewed']}", "", "run tree of the first invocation (until the approval pause) and the resume:"]  # fmt: skip
    keep = [line for line in client.tree() if not any(x in line for x in ("ChannelWrite", "RunnableSequence", "Branch", "RunnableLambda"))]
    lines += ["  " + line for line in keep]
    leaked = [
        r["name"] for r in client.recorded.values() if "KR0012345678" in json.dumps(r["inputs"], default=str) + json.dumps(r["outputs"], default=str)
    ]
    lines.append(f"spans containing the raw account number: {len(leaked)} of {len(client.recorded)}")
    return lines


async def _stream_demo() -> list[str]:
    g = build(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "stream-1"}}
    nodes, tokens = [], []
    async for ns, mode, chunk in g.astream({"messages": [{"role": "user", "content": "What are the wire transfer cutoff times?"}]}, cfg,
                                       context=t.Customer("C-100"), stream_mode=["updates", "messages"], subgraphs=True):  # fmt: skip
        if mode == "updates" and not ns:
            nodes.append(next(iter(chunk)))
        elif mode == "messages" and chunk[0].type == "AIMessageChunk" and chunk[0].content:
            tokens.append(chunk[1].get("langgraph_node"))
    return [f"node updates in order: {nodes}", f"token chunks streamed: {len(tokens)} (from nodes {sorted(set(tokens))})"]


def stream_demo() -> list[str]:
    return asyncio.run(_stream_demo())


async def _hitl_demo() -> list[str]:
    t.reset()
    g = build(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "hitl-1"}}
    ctx = t.Customer("C-200")
    first = await g.ainvoke({"messages": [{"role": "user", "content": "My card was stolen, freeze it and send a new card"}]}, cfg, context=ctx)
    req = first["__interrupt__"][0].value["action_requests"][0]
    snap = await g.aget_state(cfg)
    lines = [f"paused before {req['name']} (args {req['args']}); thread waiting at {snap.next}; ledger so far {t.LEDGER}"]
    final = await g.ainvoke(Command(resume={"decisions": [{"type": "approve"}]}), cfg, context=ctx)
    lines.append(f"colleague approved -> {final['messages'][-1].content}")
    lines.append(f"ledger after resume: {[e['action'] for e in t.LEDGER]}")
    return lines


def hitl_demo() -> list[str]:
    return asyncio.run(_hitl_demo())


@dataclass
class Monitor:
    conversations: int = 0
    runs_by_type: Counter = field(default_factory=Counter)
    tool_errors: int = 0
    tokens: int = 0
    approvals: int = 0
    guard_events: Counter = field(default_factory=Counter)


def monitor() -> list[str]:
    rec = OfflineLangSmithClient()
    exp = evals.run_experiment(recorder=rec)
    m = Monitor(conversations=exp["n"])
    for r in rec.recorded.values():
        m.runs_by_type[r["run_type"]] += 1
        if r["run_type"] == "tool" and (r["error"] or "is not permitted" in json.dumps(r["outputs"], default=str)):
            m.tool_errors += 1
        if r["run_type"] == "llm" and r["outputs"]:
            for gen in (r["outputs"].get("generations") or [[]])[0]:
                um = (gen.get("message") or {}).get("kwargs", {}).get("usage_metadata") or {}
                m.tokens += int(um.get("total_tokens", 0))
    for c in exp["cases"]:
        m.guard_events.update(c["guard_events"])
    m.approvals = sum(1 for c in exp["cases"] if c.get("hitl_correct") is not None and c["case"].startswith(("ref", "card-2", "card-3")))
    tools = m.runs_by_type["tool"]
    signals = {
        "model_calls_per_conversation": m.runs_by_type["llm"] / m.conversations,
        "tool_error_rate": m.tool_errors / max(1, tools),
        "approval_rate": m.approvals / m.conversations,
        "guard_events_per_100": 100 * sum(m.guard_events.values()) / m.conversations,
    }
    lines = [f"{m.conversations} conversations replayed from the dataset; runs recorded by type: {dict(sorted(m.runs_by_type.items()))}",
             f"tokens (simulated counts from the scripted model): {m.tokens}; guard events: {dict(sorted(m.guard_events.items()))}", "",
             f"{'signal':<30} {'value':>8} {'alert above':>12}"]  # fmt: skip
    for k, v in signals.items():
        lines.append(f"{k:<30} {v:>8.3f} {ALERTS[k]:>12.2f}{'  ALERT' if v > ALERTS[k] else ''}")
    return lines


@dataclass
class Feedback:
    run_case: str
    route: str
    score: int
    comment: str


def feedback_demo() -> list[str]:
    """Customers rate a handful of conversations; scores are stored and summarised per route."""
    store: list[Feedback] = []
    examples = {e.metadata["case"]: e for e in evals.load_examples()}
    for case in ["bal-1", "bal-3", "kb-1", "kb-2", "card-1", "card-6", "mcp-1", "ref-1"]:
        ex = examples[case]
        out = asyncio.run(evals.run_case(ex.inputs["question"], ex.inputs["customer_id"], reference=ex.outputs))
        ok = evals.answer_contains(out, ex.outputs)["score"] == 1.0
        store.append(Feedback(case, out["route"], 1 if ok else 0, "solved it" if ok else "didn't answer my question"))
    by_route: dict[str, list[int]] = {}
    for f in store:
        by_route.setdefault(f.route, []).append(f.score)
    lines = ["simulated customer thumbs (1 = up) after 8 conversations; scores derive from whether the answer had the facts the customer needed:"]
    lines += [f"  {f.run_case:<7} route={f.route:<16} score={f.score} '{f.comment}'" for f in store]
    lines += [f"  {r:<16} mean {sum(s) / len(s):.2f} over {len(s)}" for r, s in sorted(by_route.items())]
    lines.append("with LangSmith enabled each score is sent as Client.create_feedback(run_id, key='user_score', score=..., comment=...)")
    return lines


def prompts_demo() -> list[str]:
    reg = registry()
    lines = [f"prompt '{reg['name']}': production tag -> {reg['production']}"]
    for p in all_versions():
        lines.append(f"  {p.version} sha {p.sha}: {p.note}")
    lines.append("with a LangSmith account: lcstack.capstone.prompts.push_to_langsmith() publishes both versions to the prompt hub")
    return lines
