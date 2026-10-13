"""The support-desk graph: guard_input -> supervisor -> specialist (subgraph) -> validate_output.

    START -> guard_input -(blocked)-> END
                  |
              supervisor --Command(goto)--> accounts_agent | cards_agent | knowledge_agent | out_of_scope
                                                     \\_________________|_________________/
                                                                     validate_output -> END

Each specialist is a compiled create_agent graph added as a node, so its HITL interrupts surface on
the parent thread and are resumed with ``Command(resume={"decisions": [...]})``. The parent graph is
compiled with whatever checkpointer the caller passes (memory, SQLite, Postgres, or none on the Agent
Server, which supplies its own).
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command

from lcstack.capstone import agents
from lcstack.capstone import guardrails as gr
from lcstack.capstone.prompts import CITE, PromptVersion, get_prompt
from lcstack.capstone.tools import Customer
from lcstack.core.scripted import text_of

REFUSAL = "I can't act on instructions like that. I can help with your accounts, cards and Kestrel's policies."
OUT_OF_SCOPE = "I can't give investment, tax or mortgage advice here. A Kestrel adviser can help; would you like a call back?"


class Desk(MessagesState):
    route: str
    guard_flags: Annotated[list[str], add]
    validation: Annotated[list[str], add]
    prompt_version: str


def build(prompt: PromptVersion | None = None, *, guard: bool = True, checkpointer=None, store=None):
    prompt = prompt or get_prompt()
    router = agents.router(prompt)

    def guard_input(state: Desk) -> Command[Literal["supervisor", "__end__"]]:
        last = text_of(next(m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)))
        hits = gr.screen_text(last) if guard else []
        if hits:
            gr.EVENTS.append({"layer": "input_screen"})
            return Command(
                goto=END,
                update={"route": "blocked", "guard_flags": ["input_injection"], "messages": [AIMessage(REFUSAL)], "prompt_version": prompt.version},
            )
        return Command(goto="supervisor", update={"prompt_version": prompt.version})

    def supervisor(state: Desk) -> Command[Literal["accounts_agent", "cards_agent", "knowledge_agent", "out_of_scope"]]:
        last = text_of(next(m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)))
        r = router.invoke(last)
        return Command(goto=r.specialist, update={"route": r.specialist})

    def out_of_scope(state: Desk) -> dict:
        return {"messages": [AIMessage(OUT_OF_SCOPE)]}

    def validate_output(state: Desk) -> dict:
        last = state["messages"][-1]
        answer = text_of(last)
        needs_cite = (
            state.get("route") == "knowledge_agent" and CITE in prompt.text and "(source:" not in answer and "search_kb" in str(state["messages"])
        )
        if not guard:
            return {}
        fixed, issues = gr.validate_output(answer, needs_citation=needs_cite)
        if not issues:
            return {}
        return {"messages": [AIMessage(fixed, id=last.id)], "validation": issues}

    b = StateGraph(Desk, context_schema=Customer)
    b.add_node("guard_input", guard_input)
    b.add_node("supervisor", supervisor)
    for name in agents.ALLOWED:
        b.add_node(name, agents.specialist(name, prompt, guard=guard))
        b.add_edge(name, "validate_output")
    b.add_node("out_of_scope", out_of_scope)
    b.add_node("validate_output", validate_output)
    b.add_edge(START, "guard_input")
    b.add_edge("out_of_scope", "validate_output")
    b.add_edge("validate_output", END)
    return b.compile(checkpointer=checkpointer, store=store, name="support_desk")
