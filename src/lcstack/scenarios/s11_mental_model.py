"""11 LangGraph Mental Model: shared state, nodes that return partial updates, edges, super-steps.

Client: Halsey Vale Health's emergency-department intake. When a patient registers, vitals scoring and
insurance eligibility run at the same time (they do not depend on each other), then a triage node
combines both. The scenario shows that the two run in one super-step and that state is checkpointed
after every step.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from lcstack.core.companies import HEALTHCARE
from lcstack.scenarios import Meta

META = Meta(11, "LangGraph Mental Model", "Shared state, nodes as functions returning partial updates, fixed edges, fan-out/fan-in, super-steps, a checkpoint per step",
            f"{HEALTHCARE}: emergency-department intake", "healthcare", "mental-model")  # fmt: skip


class Intake(TypedDict, total=False):
    patient_id: str
    heart_rate: int
    systolic: int
    payer: str
    news_score: int  # written by `vitals`
    eligible: bool  # written by `insurance`
    acuity: str  # written by `triage`


def vitals(s: Intake) -> dict:
    score = (2 if s["heart_rate"] > 110 else 0) + (3 if s["systolic"] < 90 else 0)
    return {"news_score": score}


def insurance(s: Intake) -> dict:
    return {"eligible": s["payer"] in {"Halsey Vale Plan", "State Medicaid", "Northcoast Mutual"}}


def triage(s: Intake) -> dict:
    acuity = "resuscitation bay" if s["news_score"] >= 5 else "urgent" if s["news_score"] >= 2 else "standard"
    return {"acuity": acuity + ("" if s["eligible"] else " (financial counselling referral)")}


def build():
    b = StateGraph(Intake)
    b.add_node("vitals", vitals)
    b.add_node("insurance", insurance)
    b.add_node("triage", triage)
    b.add_edge(START, "vitals")
    b.add_edge(START, "insurance")  # fan out: both start in the same super-step
    b.add_edge(["vitals", "insurance"], "triage")  # fan in: triage waits for both
    b.add_edge("triage", END)
    return b.compile(checkpointer=InMemorySaver())


def run() -> list[str]:
    g = build()
    cfg = {"configurable": {"thread_id": "ed-visit-2291"}}
    out = [f"{HEALTHCARE} - ED intake graph", "", "graph (mermaid, generated from the compiled graph):"]
    out += ["  " + line for line in g.get_graph().draw_mermaid().splitlines() if "-->" in line or "-.->" in line]
    out += ["", "stream_mode='updates' (each node returns only the keys it owns):"]
    chunks = list(g.stream({"patient_id": "P-2291", "heart_rate": 124, "systolic": 86, "payer": "Unknown Assurance"}, cfg, stream_mode="updates"))
    # vitals and insurance finish in the same super-step in either order; sort them so the output is stable
    chunks[:2] = sorted(chunks[:2], key=lambda c: next(iter(c)))
    out += [f"  {c}" for c in chunks]
    out += ["", "checkpoints, oldest first (step -> nodes scheduled next):"]
    for snap in reversed(list(g.get_state_history(cfg))):
        out.append(f"  step {snap.metadata['step']:>2}: next={snap.next}")
    final = g.get_state(cfg).values
    out.append(f"final state: acuity={final['acuity']!r}, news_score={final['news_score']}, eligible={final['eligible']}")
    return out
