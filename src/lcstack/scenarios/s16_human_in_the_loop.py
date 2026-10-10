"""16 Human in the Loop: interrupt, inspect, resume with Command; keep side effects idempotent.

Client: Quillmere Home Loans' document review. An extraction step reads the borrower's documents and
proposes conditions; an underwriter must approve, edit or reject before anything is written to the loan
origination system (LOS). The scenario also shows the classic bug: a node that posts to the LOS before
its interrupt posts twice, because on resume the node runs again from its first line.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from lcstack.core.companies import MORTGAGE
from lcstack.scenarios import Meta

META = Meta(16, "Human in the Loop", "interrupt() payloads, __interrupt__, Command(resume=...), approve/edit/reject, idempotent side effects, a checkpointer is required",
            f"{MORTGAGE}: underwriter approval of document conditions", "mortgage", "human-in-the-loop")  # fmt: skip


class Review(TypedDict, total=False):
    loan_id: str
    conditions: list[str]
    decision: str
    posted: list[str]


class LOS:
    """Fake loan origination system that counts writes, so duplicate side effects are visible."""

    def __init__(self) -> None:
        self.writes: list[str] = []
        self._keys: set[str] = set()

    def post(self, text: str) -> None:
        self.writes.append(text)

    def post_once(self, key: str, text: str) -> None:
        """Idempotent write: the same key is applied once, however often the node re-runs."""
        if key not in self._keys:
            self._keys.add(key)
            self.writes.append(text)


def extract(s: Review) -> dict:
    return {"conditions": ["verify 2 most recent pay stubs", "explain 6,000.00 deposit on statement", "gift letter for 20,000.00"]}


def build(los: LOS, *, buggy: bool = False):
    def underwriter_review(s: Review) -> dict:
        if buggy:
            los.post(f"{s['loan_id']}: review started")  # side effect BEFORE interrupt: runs again on resume
        else:
            los.post_once(f"{s['loan_id']}:review-started", f"{s['loan_id']}: review started")
        answer = interrupt({"loan_id": s["loan_id"], "proposed_conditions": s["conditions"], "allowed": ["approve", "edit", "reject"]})
        if answer["action"] == "reject":
            return {"decision": "rejected", "conditions": []}
        conditions = answer.get("conditions", s["conditions"])
        return {"decision": "approved" if answer["action"] == "approve" else "edited", "conditions": conditions}

    def post_conditions(s: Review) -> dict:
        for c in s["conditions"]:  # after the interrupt: runs once, with the human's decision
            los.post_once(f"{s['loan_id']}:{c}", f"{s['loan_id']}: condition '{c}'")
        return {"posted": s["conditions"]}

    b = StateGraph(Review)
    b.add_node("extract", extract)
    b.add_node("underwriter_review", underwriter_review)
    b.add_node("post_conditions", post_conditions)
    b.add_edge(START, "extract")
    b.add_edge("extract", "underwriter_review")
    b.add_edge("underwriter_review", "post_conditions")
    b.add_edge("post_conditions", END)
    return b


def run() -> list[str]:
    out = [f"{MORTGAGE} - underwriter review with interrupt", ""]
    los = LOS()
    g = build(los).compile(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "QH-5120"}}
    paused = g.invoke({"loan_id": "QH-5120"}, cfg)
    payload = paused["__interrupt__"][0].value
    out.append(f"paused: next={g.get_state(cfg).next}; payload proposed {len(payload['proposed_conditions'])} conditions")
    edited = [c for c in payload["proposed_conditions"] if "deposit" not in c] + ["verify employment by phone"]
    final = g.invoke(Command(resume={"action": "edit", "conditions": edited}), cfg)
    out.append(f"resumed with an edit -> decision={final['decision']!r}, posted={final['posted']}")
    out.append(f"LOS writes (idempotent node): {len(los.writes)} -> {los.writes[0]!r} + {len(los.writes) - 1} conditions")

    los2 = LOS()
    g2 = build(los2).compile(checkpointer=InMemorySaver())
    c2 = {"configurable": {"thread_id": "QH-5121"}}
    g2.invoke({"loan_id": "QH-5121"}, c2)
    r = g2.invoke(Command(resume={"action": "reject"}), c2)
    out.append(f"reject path -> decision={r['decision']!r}, conditions posted={r['posted']}, LOS writes={len(los2.writes)}")

    bug = LOS()
    g3 = build(bug, buggy=True).compile(checkpointer=InMemorySaver())
    c3 = {"configurable": {"thread_id": "QH-5122"}}
    g3.invoke({"loan_id": "QH-5122"}, c3)
    g3.invoke(Command(resume={"action": "approve"}), c3)
    dupes = bug.writes.count("QH-5122: review started")
    out.append(f"non-idempotent version: 'review started' written {dupes} times (the node re-ran from its first line on resume)")

    no_cp = build(LOS()).compile()
    first = no_cp.invoke({"loan_id": "QH-5123"})
    try:
        no_cp.invoke(Command(resume={"action": "approve"}))
        out.append("no checkpointer: resumed (unexpected)")
    except RuntimeError as exc:
        out.append(f"no checkpointer: the pause happens ({'__interrupt__' in first}) but resuming fails: {exc}")
    return out
