"""Checkpointer helpers with an explicit deserialisation allowlist.

LangGraph checkpoints are msgpack. Custom types (a Pydantic structured response, a dataclass in state)
are only revived when they are on the serializer's allowlist; unlisted types log a warning today and
will be blocked in a future version (``LANGGRAPH_STRICT_MSGPACK=true`` blocks them now). Listing the
types we store is both quieter and safer: a tampered checkpoint cannot revive an arbitrary class.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


def serde(*types: type) -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=list(types))


def memory_saver(*types: type) -> InMemorySaver:
    return InMemorySaver(serde=serde(*types))
