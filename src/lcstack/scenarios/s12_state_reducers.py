"""12 State and Reducers: how concurrent and repeated updates are merged.

Client: Wrenfield Grocers' basket-assistant graph. Messages must merge by id (an edited message
replaces, not duplicates), applied promotions accumulate across turns, the route is simply overwritten,
substitutions from two parallel pickers must be combined without duplicates, and at checkout the promo
list must be reset even though its reducer appends.
"""

from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Overwrite

from lcstack.core.companies import RETAIL
from lcstack.scenarios import Meta

META = Meta(12, "State and Reducers", "add_messages (merge by id, RemoveMessage), operator.add, plain overwrite, a custom reducer, Overwrite to bypass a reducer",
            f"{RETAIL}: basket assistant state", "retail", "state-reducers")  # fmt: skip


def union(left: list[str] | None, right: list[str] | None) -> list[str]:
    """Custom reducer: sorted set union, so two pickers suggesting the same substitute count once."""
    return sorted(set(left or []) | set(right or []))


class Basket(TypedDict, total=False):
    messages: Annotated[list, add_messages]  # append, merge by id
    promos: Annotated[list[str], add]  # concatenate
    substitutions: Annotated[list[str], union]  # custom
    route: str  # no reducer: last write wins


def picker_a(s: Basket) -> dict:
    return {"substitutions": ["oat milk 1L", "rye bread"]}


def picker_b(s: Basket) -> dict:
    return {"substitutions": ["rye bread", "free-range eggs x6"]}


def apply_promos(s: Basket) -> dict:
    return {"promos": ["MEMBER5"], "route": "checkout"}


def build():
    b = StateGraph(Basket)
    for name, fn in [("picker_a", picker_a), ("picker_b", picker_b), ("apply_promos", apply_promos)]:
        b.add_node(name, fn)
    b.add_edge(START, "picker_a")
    b.add_edge(START, "picker_b")
    b.add_edge(["picker_a", "picker_b"], "apply_promos")
    b.add_edge("apply_promos", END)
    return b.compile(checkpointer=InMemorySaver())


def run() -> list[str]:
    g = build()
    cfg = {"configurable": {"thread_id": "basket-88"}}
    out = [f"{RETAIL} - basket state and reducers", ""]
    g.invoke({"messages": [HumanMessage("Add milk and bread", id="m1")], "route": "browse"}, cfg)
    s = g.get_state(cfg).values
    out.append(f"turn 1: promos={s['promos']} substitutions={s['substitutions']} route={s['route']!r} messages={len(s['messages'])}")
    g.invoke({"messages": [AIMessage("Added.", id="m2")]}, cfg)
    s = g.get_state(cfg).values
    out.append(f"turn 2: promos={s['promos']}  <- operator.add appended again (state grows every run)")
    g.update_state(cfg, {"messages": [HumanMessage("Add oat milk and bread", id="m1")]})
    s = g.get_state(cfg).values
    out.append(f"edit message m1 (same id): messages={len(s['messages'])}, first={s['messages'][0].content!r}  <- add_messages replaced it")
    g.update_state(cfg, {"messages": [RemoveMessage(id="m2")]})
    out.append(f"RemoveMessage(id='m2'): messages={len(g.get_state(cfg).values['messages'])}")
    g.update_state(cfg, {"promos": ["STAFF10"]})
    out.append(f"update_state(promos=['STAFF10']) goes through the reducer: {g.get_state(cfg).values['promos']}")
    g.update_state(cfg, {"promos": Overwrite(["STAFF10"])})
    out.append(f"update_state(promos=Overwrite(['STAFF10'])) bypasses it: {g.get_state(cfg).values['promos']}")
    out.append(f"custom union reducer merged two parallel pickers without duplicates: {g.get_state(cfg).values['substitutions']}")
    return out
