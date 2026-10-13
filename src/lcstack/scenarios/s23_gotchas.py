"""23 Gotchas: the bugs everyone hits once, each reproduced (broken) and then fixed.

Client: Halsey Vale Health's pharmacy refill workflow. Every gotcha below was written as a failing case
first, then fixed; tests/test_s23_gotchas.py asserts the broken symptom AND the fix, so a library
upgrade that changes either behaviour is noticed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from operator import add
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command, Overwrite, interrupt

from lcstack.core.companies import HEALTHCARE
from lcstack.core.persist import memory_saver
from lcstack.scenarios import Meta

META = Meta(23, "Gotchas", "Missing compile, new thread_id per call, recursion limit placement, reducer growth vs Overwrite, static edge + Command double-run, re-run after interrupt, checkpoint type allowlist",
            f"{HEALTHCARE}: pharmacy refill workflow, broken then fixed", "healthcare", "gotchas")  # fmt: skip


class Refill(TypedDict, total=False):
    rx: str
    checks: Annotated[list[str], add]
    attempts: int
    route: str


# 1. Graph has no invoke --------------------------------------------------------------------------
def g1_builder() -> StateGraph:
    b = StateGraph(Refill)
    b.add_node("verify", lambda s: {"checks": ["verified"]})
    b.add_edge(START, "verify")
    return b


def g1_broken() -> str:
    try:
        g1_builder().invoke({"rx": "RX-1"})  # type: ignore[attr-defined]
        return "ran"
    except AttributeError as e:
        return f"AttributeError: {str(e).split(' object')[0]} object has no invoke"


def g1_fixed() -> str:
    return f"checks={g1_builder().compile().invoke({'rx': 'RX-1'})['checks']}"


# 2. Memory lost between turns --------------------------------------------------------------------
def g2_graph():
    b = StateGraph(MessagesState)
    b.add_node("echo", lambda s: {"messages": [("ai", f"I have {len(s['messages'])} messages on this thread")]})
    b.add_edge(START, "echo")
    return b.compile(checkpointer=InMemorySaver())


def g2_turns(same_thread: bool) -> str:
    g, n = g2_graph(), 0
    for i in range(3):
        tid = "refill-chat" if same_thread else f"refill-chat-{i}"  # broken version mints a new id per call
        n = len(g.invoke({"messages": [("user", f"turn {i}")]}, {"configurable": {"thread_id": tid}})["messages"])
    return f"messages after 3 turns = {n}"


# 3. GraphRecursionError -------------------------------------------------------------------------
def g3_graph(with_exit: bool):
    b = StateGraph(Refill)
    b.add_node("call_prescriber", lambda s: {"attempts": s.get("attempts", 0) + 1})
    b.add_edge(START, "call_prescriber")
    if with_exit:
        b.add_conditional_edges("call_prescriber", lambda s: END if s["attempts"] >= 3 else "call_prescriber")
    else:
        b.add_edge("call_prescriber", "call_prescriber")  # retries forever
    return b.compile()


def g3_broken() -> str:
    try:
        g3_graph(False).invoke({"rx": "RX-3"}, {"configurable": {"recursion_limit": 5}})  # wrong place: ignored
        return "finished"
    except GraphRecursionError:
        pass
    try:
        g3_graph(False).invoke({"rx": "RX-3"}, {"recursion_limit": 5})  # right place, but the loop still has no exit
        return "finished"
    except GraphRecursionError:
        return "GraphRecursionError (limit inside 'configurable' is ignored; top-level limit only stops it sooner)"


def g3_fixed() -> str:
    return f"attempts={g3_graph(True).invoke({'rx': 'RX-3'}, {'recursion_limit': 10})['attempts']} then exit"


# 4. List state keeps growing --------------------------------------------------------------------
def g4_run(reset: bool) -> str:
    b = StateGraph(Refill)
    b.add_node("check", lambda s: {"checks": Overwrite(["allergy", "interaction"]) if reset else ["allergy", "interaction"]})
    b.add_edge(START, "check")
    g = b.compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "rx-4"}}
    for _ in range(3):
        g.invoke({"rx": "RX-4"}, cfg)
    return f"checks after 3 runs = {len(g.get_state(cfg).values['checks'])}"


# 5. Two branches ran ----------------------------------------------------------------------------
def g5_run(static_edge_too: bool) -> str:
    def route(s: Refill) -> Command[Literal["pharmacist", "auto_fill"]]:
        return Command(update={"route": "pharmacist"}, goto="pharmacist")

    b = StateGraph(Refill)
    b.add_node("route", route)
    b.add_node("pharmacist", lambda s: {"checks": ["pharmacist review"]})
    b.add_node("auto_fill", lambda s: {"checks": ["AUTO-FILLED"]})
    b.add_edge(START, "route")
    if static_edge_too:
        b.add_edge("route", "auto_fill")  # also runs, in addition to the Command target
    return f"ran: {sorted(b.compile().invoke({'rx': 'RX-5', 'checks': []})['checks'])}"


# 6. Duplicate side effects after interrupt ------------------------------------------------------
def g6_run(idempotent: bool) -> str:
    sent: list[str] = []
    done: set[str] = set()

    def notify_then_ask(s: Refill) -> dict:
        key = f"{s['rx']}:sms"
        if not idempotent or key not in done:
            sent.append("SMS: refill under review")  # side effect before the interrupt
            done.add(key)
        answer = interrupt("approve refill?")
        return {"checks": [f"pharmacist said {answer}"]}

    b = StateGraph(Refill)
    b.add_node("ask", notify_then_ask)
    b.add_edge(START, "ask")
    g = b.compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "rx-6"}}
    g.invoke({"rx": "RX-6"}, cfg)
    g.invoke(Command(resume="yes"), cfg)
    return f"SMS sent {len(sent)} time(s)"


# 7. Custom types in checkpoints (found while building this repo) --------------------------------
@dataclass
class Prescription:
    """A dataclass in state; checkpoints must be told it is safe to revive."""

    drug: str


class RxState(TypedDict, total=False):
    rx: Prescription


def g7_run(allowlisted: bool) -> str:
    records: list[str] = []

    class Grab(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    log = logging.getLogger("langgraph")
    h = Grab(level=logging.WARNING)
    log.addHandler(h)
    try:
        b = StateGraph(RxState)
        b.add_node("noop", lambda s: {})
        b.add_edge(START, "noop")
        saver = memory_saver(Prescription) if allowlisted else InMemorySaver()
        g = b.compile(checkpointer=saver)
        cfg = {"configurable": {"thread_id": f"rx-7-{allowlisted}"}}
        g.invoke({"rx": Prescription("amoxicillin")}, cfg)
        drug = g.get_state(cfg).values["rx"].drug
    finally:
        log.removeHandler(h)
    warned = any("unregistered type" in r for r in records)
    return f"revived drug={drug!r}, warning logged={warned}"


GOTCHAS = [
    ("Graph has no invoke", "forgot builder.compile()", g1_broken, g1_fixed),
    ("Memory lost between turns", "new thread_id each call", lambda: g2_turns(False), lambda: g2_turns(True)),
    ("GraphRecursionError", "loop has no exit; recursion_limit put inside configurable", g3_broken, g3_fixed),
    ("List state keeps growing", "reducer appends on every run", lambda: g4_run(False), lambda: g4_run(True)),
    ("Two branches ran", "a node had both a Command goto and a fixed edge", lambda: g5_run(True), lambda: g5_run(False)),
    ("Duplicate side effects", "node re-ran from its first line after interrupt", lambda: g6_run(False), lambda: g6_run(True)),
    ("Checkpoint revives unknown class", "custom type not on the serializer allowlist", lambda: g7_run(False), lambda: g7_run(True)),
]


def run() -> list[str]:
    out = [f"{HEALTHCARE} - pharmacy refill gotchas, broken then fixed", ""]
    for i, (symptom, cause, broken, fixed) in enumerate(GOTCHAS, 1):
        out.append(f"{i}. {symptom} ({cause})")
        out.append(f"   broken: {broken()}")
        out.append(f"   fixed : {fixed()}")
    return out
