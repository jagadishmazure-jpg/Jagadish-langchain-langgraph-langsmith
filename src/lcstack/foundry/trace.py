"""In-process trace hook for the Foundry host.

The live ``langchain-azure-ai`` package can export OpenTelemetry spans to Application Insights
when the platform sets ``APPLICATIONINSIGHTS_CONNECTION_STRING``. This hook keeps the same
idea locally: one operation per LangGraph run, with message text and tool arguments omitted
unless content recording is turned on. It never opens a socket.
"""

from __future__ import annotations

from typing import Any

from lcstack.core.tracing import LocalTraceRecorder


def _flatten(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return "" if value is None else str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, dict):
        return " ".join(_flatten(item) for item in value.values())
    if isinstance(value, list | tuple):
        return " ".join(_flatten(item) for item in value)
    content = getattr(value, "content", None)
    if content is not None and content is not value:
        return _flatten(content)
    return ""


class FoundryTraceHook:
    """Records graph runs for the host. ``record_content`` is the capture switch for message text."""

    def __init__(self, *, record_content: bool = False) -> None:
        self.record_content = record_content
        self.operations: list[dict] = []

    def recorder(self) -> LocalTraceRecorder:
        return LocalTraceRecorder()

    def collect(self, recorder: LocalTraceRecorder, *, response_id: str, caller_id: str) -> None:
        for run in recorder.roots:
            self._walk(run, 0, response_id, caller_id)

    def _walk(self, run: Any, depth: int, response_id: str, caller_id: str) -> None:
        operation: dict[str, Any] = {
            "response_id": response_id,
            "name": run.name,
            "kind": run.run_type,
            "depth": depth,
            "caller_id": caller_id,
            "content": "recorded" if self.record_content else "redacted",
        }
        if self.record_content:
            operation["inputs"] = _flatten(run.inputs)
            operation["outputs"] = _flatten(run.outputs)
        self.operations.append(operation)
        children = sorted(run.child_runs or [], key=lambda child: child.dotted_order or "")
        for child in children:
            self._walk(child, depth + 1, response_id, caller_id)

    def contains_text(self, needle: str) -> bool:
        blob = " ".join(_flatten(op) for op in self.operations)
        return needle in blob

    def tool_names(self) -> list[str]:
        return sorted({op["name"] for op in self.operations if op["kind"] == "tool"})
