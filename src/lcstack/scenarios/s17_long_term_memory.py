"""17 Long-Term Memory: stores that persist across threads, scoped by namespace, searchable by meaning.

Client: Halsey Vale Health's appointment-scheduling assistant. A patient says once that they prefer
morning appointments and need step-free access; weeks later, in a brand-new conversation (a new
thread), the assistant should still know. One patient's preferences must never surface for another.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.runtime import Runtime
from langgraph.store.memory import InMemoryStore

from lcstack.core.companies import HEALTHCARE
from lcstack.core.embeddings import HashingEmbeddings
from lcstack.core.scripted import Intent, Playbook, Turn, scripted
from lcstack.scenarios import Meta

META = Meta(17, "Long-Term Memory", "InMemoryStore with an embedding index, namespaces per user, runtime.store in nodes and tools, context_schema, cross-thread recall",
            f"{HEALTHCARE}: appointment-scheduling assistant that remembers preferences", "healthcare", "long-term-memory")  # fmt: skip


@dataclass
class Patient:
    patient_id: str


def make_store() -> InMemoryStore:
    emb = HashingEmbeddings()
    return InMemoryStore(index={"dims": emb.dim, "embed": emb.embed_documents, "fields": ["text"]})


def remember(state: MessagesState, runtime: Runtime[Patient]) -> dict:
    """Graph node: save any stated preference into the patient's namespace."""
    text = state["messages"][-1].content
    if re.search(r"\bprefer|\bneed\b", text, re.I):
        ns = ("patients", runtime.context.patient_id, "preferences")
        key = f"pref-{len(runtime.store.search(ns, limit=100)) + 1}"
        runtime.store.put(ns, key, {"text": text})
    return {}


@tool
def recall_preferences(topic: str, runtime: ToolRuntime[Patient]) -> str:
    """Search what this patient told us before (only their own namespace)."""
    ns = ("patients", runtime.context.patient_id, "preferences")
    items = runtime.store.search(ns, query=topic, limit=2)
    return " | ".join(i.value["text"] for i in items) or "no saved preferences"


@tool
def find_slots(clinic: str, morning_only: bool, step_free: bool) -> str:
    """Find open appointment slots at a clinic."""
    slots = [("Tue 08:40", True, True), ("Tue 14:10", False, True), ("Wed 09:20", True, False), ("Thu 10:00", True, True)]
    keep = [t for t, am, sf in slots if (am or not morning_only) and (sf or not step_free)]
    return f"{clinic}: {', '.join(keep)}"


def _answer(t: Turn) -> str:
    return f"Based on what you told us before ({t.results.get('recall_preferences')}), open slots: {t.results.get('find_slots')}"


PLAYBOOK = Playbook(intents=[Intent("book", r"book|appointment", steps=[
    lambda t: ("recall_preferences", {"topic": "appointment time and access needs"}),
    lambda t: ("find_slots", {"clinic": "Cardiology", "morning_only": "morning" in t.results.get("recall_preferences", "").lower(),
                              "step_free": "step-free" in t.results.get("recall_preferences", "").lower()}),
], answer=_answer)])  # fmt: skip


def build_memory_graph(store):
    b = StateGraph(MessagesState, context_schema=Patient)
    b.add_node("remember", remember)
    b.add_edge(START, "remember")
    return b.compile(checkpointer=InMemorySaver(), store=store)


def run() -> list[str]:
    store = make_store()
    mem = build_memory_graph(store)
    out = [f"{HEALTHCARE} - scheduling assistant with long-term memory", ""]
    for pid, thread, text in [
        ("P-301", "chat-1", "I prefer morning appointments, before 11."),
        ("P-301", "chat-1", "I also need step-free access, I use a wheelchair."),
        ("P-302", "chat-9", "I prefer late afternoons."),
    ]:
        mem.invoke({"messages": [{"role": "user", "content": text}]}, {"configurable": {"thread_id": thread}}, context=Patient(pid))
    out.append(f"store namespaces: {sorted(store.list_namespaces())}")
    hits = store.search(("patients", "P-301", "preferences"), query="wheelchair access", limit=1)
    out.append(f"semantic search in P-301 for 'wheelchair access': {hits[0].value['text']!r} (score {hits[0].score:.2f})")

    agent = create_agent(
        scripted(PLAYBOOK, name="scheduler"), [recall_preferences, find_slots], context_schema=Patient, store=store, checkpointer=InMemorySaver()
    )
    ask = {"messages": [{"role": "user", "content": "Please book a cardiology appointment."}]}
    a = agent.invoke(ask, {"configurable": {"thread_id": "chat-NEW-1"}}, context=Patient("P-301"))
    out.append(f"P-301, new thread: {a['messages'][-1].content}")
    b = agent.invoke(ask, {"configurable": {"thread_id": "chat-NEW-2"}}, context=Patient("P-303"))
    out.append(f"P-303 (never stated anything), new thread: {b['messages'][-1].content}")
    out.append("checkpointer = this conversation's short-term state; store = facts shared across that patient's threads")
    return out
