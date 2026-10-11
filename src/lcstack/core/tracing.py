"""LangSmith switches and an offline trace recorder.

Tracing goes to LangSmith only when BOTH ``LANGSMITH_TRACING=true`` and ``LANGSMITH_API_KEY`` are set.
Otherwise :func:`ensure_offline` turns tracing off so nothing tries to reach the network, and
:class:`LocalTraceRecorder` (a LangChain ``BaseTracer``) keeps the same run tree in memory: every model
call, tool call and graph node becomes a run with inputs, outputs, tags, metadata, token usage and
errors, which is exactly the shape LangSmith stores. Monitoring and the capstone read from it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tracers.base import BaseTracer
from langchain_core.tracers.schemas import Run
from langsmith import Client


def langsmith_enabled() -> bool:
    return os.getenv("LANGSMITH_TRACING", "").lower() == "true" and bool(os.getenv("LANGSMITH_API_KEY"))


def ensure_offline() -> str:
    """Disable LangSmith tracing unless both switches are set. Returns the mode in force."""
    if langsmith_enabled():
        return "langsmith"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ.pop("LANGCHAIN_TRACING_V2", None)
    return "local"


@dataclass
class Span:
    name: str
    run_type: str
    depth: int
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    tokens: int = 0
    error: str | None = None
    latency_ms: float = 0.0


class LocalTraceRecorder(BaseTracer):
    """Collects finished root runs; ``spans()`` flattens them depth-first like the LangSmith trace view."""

    def __init__(self) -> None:
        super().__init__()
        self.roots: list[Run] = []

    def _persist_run(self, run: Run) -> None:
        self.roots.append(run)

    def spans(self) -> list[Span]:
        out: list[Span] = []

        def walk(r: Run, d: int) -> None:
            tokens = 0
            if r.run_type == "llm" and r.outputs:
                for gen in (r.outputs.get("generations") or [[]])[0]:
                    um = (gen.get("message") or {}).get("kwargs", {}).get("usage_metadata") or {}
                    tokens += int(um.get("total_tokens", 0))
            meta = {k: v for k, v in (r.extra or {}).get("metadata", {}).items() if not k.startswith(("langgraph_", "checkpoint_", "ls_", "__"))}
            lat = (r.end_time - r.start_time).total_seconds() * 1000 if r.end_time and r.start_time else 0.0
            out.append(Span(r.name, r.run_type, d, list(r.tags or []), meta, tokens, (r.error or None) and r.error.splitlines()[0], lat))
            for c in sorted(r.child_runs, key=lambda c: c.dotted_order or ""):
                walk(c, d + 1)

        for r in self.roots:
            walk(r, 0)
        return out

    def tree(self, *, max_depth: int = 6, skip_internal: bool = True) -> list[str]:
        lines = []
        for s in self.spans():
            if s.depth > max_depth:
                continue
            if (
                skip_internal
                and s.run_type == "chain"
                and s.name in {"RunnableSequence", "RunnableLambda", "ChannelWrite", "Branch", "RunnableCallable"}
            ):
                continue
            extra = f" tokens={s.tokens}" if s.tokens else ""
            extra += f" tags={s.tags}" if s.tags and s.depth == 0 else ""
            extra += f" ERROR={s.error}" if s.error else ""
            lines.append(f"{'  ' * s.depth}{s.run_type:<5} {s.name}{extra}")
        return lines


class OfflineLangSmithClient(Client):
    """A ``langsmith.Client`` that records what it WOULD send to LangSmith and never opens a socket.

    LangSmith's tracers call ``create_run`` / ``update_run`` on the client; this subclass keeps those
    payloads in ``self.recorded`` (keyed by run id) instead of posting them. Use it with
    ``langsmith.tracing_context(enabled=True, client=...)`` to inspect real LangSmith run trees, tags,
    metadata and redaction offline. The API URL points at a closed local port as a second safety net.
    """

    def __init__(self, *, hide_inputs=None, hide_outputs=None) -> None:
        super().__init__(
            api_url="http://127.0.0.1:9", api_key="offline-no-network", auto_batch_tracing=False, hide_inputs=hide_inputs, hide_outputs=hide_outputs
        )
        self.recorded: dict[str, dict] = {}
        self.order: list[str] = []

    def create_run(self, name, inputs, run_type, *args, **kwargs):
        rid = str(kwargs.get("id"))
        self.order.append(rid)
        extra = kwargs.get("extra") or {}
        skip = ("ls_", "langgraph_", "checkpoint_", "__", "revision_id", "LANGSMITH_")
        self.recorded[rid] = {
            "name": name,
            "run_type": run_type,
            "inputs": self._hide_run_inputs(inputs),  # the same masking hook the real client applies
            "parent": str(kwargs.get("parent_run_id")) if kwargs.get("parent_run_id") else None,
            "tags": list(kwargs.get("tags") or []),
            "metadata": {k: v for k, v in (extra.get("metadata") or {}).items() if not k.startswith(skip)},
            "outputs": None,
            "error": None,
        }

    def update_run(self, run_id, **kwargs):
        r = self.recorded.get(str(run_id))
        if r is not None:
            r["outputs"] = self._hide_run_outputs(kwargs["outputs"]) if kwargs.get("outputs") else r["outputs"]
            r["error"] = kwargs.get("error") or r["error"]

    def tree(self) -> list[str]:
        children: dict[str | None, list[str]] = {}
        for rid in self.order:
            children.setdefault(self.recorded[rid]["parent"], []).append(rid)
        lines: list[str] = []

        def walk(rid: str, d: int) -> None:
            r = self.recorded[rid]
            meta = f" metadata={r['metadata']}" if d == 0 and r["metadata"] else ""
            tags = f" tags={r['tags']}" if d == 0 and r["tags"] else ""
            lines.append(f"{'  ' * d}{r['run_type']:<6} {r['name']}{tags}{meta}{' ERROR' if r['error'] else ''}")
            for c in children.get(rid, []):
                walk(c, d + 1)

        for root in children.get(None, []):
            walk(root, 0)
        return lines


def deep_mask(pattern, replacement: str):
    """Build a hide_inputs/hide_outputs function that masks ``pattern`` in every string, however nested."""

    def walk(v):
        if isinstance(v, str):
            return pattern.sub(replacement, v)
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list | tuple):
            return type(v)(walk(x) for x in v)
        if isinstance(v, BaseMessage):  # LangChain passes live message objects; copy, never mutate state
            update = {"content": walk(v.content)}
            if isinstance(v, AIMessage) and v.tool_calls:
                update["tool_calls"] = [{**tc, "args": walk(tc["args"])} for tc in v.tool_calls]
            return v.model_copy(update=update)
        return v

    return walk
