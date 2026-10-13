"""Guardrails for the support desk: injection screening, PII, tool allowlists, output validation.

Layers, outermost first (each is tested on its own and as part of the evaluation ablation):
  1. ``screen_text`` on the customer's message (guard_input node): instruction-override attempts are refused.
  2. ``ScreenToolOutputs`` (wrap_tool_call): retrieved documents and tool results that contain
     instruction-like text are quarantined before the model sees them (indirect prompt injection).
  3. ``PIIMiddleware``: card numbers masked and account numbers hashed in inputs and tool results.
  4. ``ToolAllowlist`` (wrap_tool_call): a specialist can only execute its own tools.
  5. ``HumanInTheLoopMiddleware``: money-moving and card-reissue tools pause for a colleague.
  6. ``validate_output``: the final answer must not contain full account or card numbers or promises
     the bank does not make, and policy answers must cite a source when the prompt requires it.
"""

from __future__ import annotations

import re

from langchain.agents.middleware import AgentMiddleware, PIIMiddleware
from langchain_core.messages import ToolMessage

INJECTION = [
    re.compile(p, re.I)
    for p in (
        r"ignore (all |any )?(your |the |previous |prior )?(instructions|rules|guidelines)",
        r"assistant instruction",
        r"system (override|prompt)",
        r"you are now (in )?(developer|admin|dan)",
        r"call \w+ with \{",
        r"(reveal|tell|show) .{0,40}(full|whole) .{0,20}(account|card) number",
    )
]
ACCOUNT = re.compile(r"\bKR\d{10}\b")
CARD = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
PROMISES = re.compile(r"\b(guarantee[ds]?|risk-free|always approved)\b", re.I)

EVENTS: list[dict] = []  # guard events of the current process (evaluations reset it per example)


def screen_text(text: str) -> list[str]:
    """Names of the injection patterns found in ``text`` (empty when clean)."""
    return [p.pattern for p in INJECTION if p.search(text)]


class ScreenToolOutputs(AgentMiddleware):
    """Quarantine instruction-like text in tool results before the model reads it (sync and async)."""

    def _screen(self, request, result):
        if isinstance(result, ToolMessage) and isinstance(result.content, str) and screen_text(result.content):
            kept = [line for line in result.content.splitlines() if not screen_text(line)]
            EVENTS.append({"layer": "tool_output_screen", "tool": request.tool_call["name"]})
            return result.model_copy(update={"content": "\n".join(kept) + "\n[quarantined: instruction-like text removed by the bank's screen]"})
        return result

    def wrap_tool_call(self, request, handler):
        return self._screen(request, handler(request))

    async def awrap_tool_call(self, request, handler):
        return self._screen(request, await handler(request))


class ToolAllowlist(AgentMiddleware):
    """Refuse to execute any tool outside the specialist's allowlist (defence in depth)."""

    def __init__(self, agent: str, allowed: set[str]) -> None:
        super().__init__()
        self.agent, self.allowed = agent, allowed

    @property
    def name(self) -> str:
        return f"ToolAllowlist[{self.agent}]"

    def _deny(self, request):
        nm = request.tool_call["name"]
        if nm in self.allowed:
            return None
        EVENTS.append({"layer": "allowlist", "tool": nm, "agent": self.agent})
        return ToolMessage(f"Tool {nm} is not permitted for the {self.agent}.", tool_call_id=request.tool_call["id"], status="error")

    def wrap_tool_call(self, request, handler):
        return self._deny(request) or handler(request)

    async def awrap_tool_call(self, request, handler):
        return self._deny(request) or await handler(request)


screen_tool_outputs = ScreenToolOutputs()


def tool_allowlist(agent: str, allowed: set[str]) -> ToolAllowlist:
    return ToolAllowlist(agent, allowed)


def account_detector(text: str) -> list[dict]:
    return [{"type": "account_number", "value": m.group(0), "start": m.start(), "end": m.end()} for m in ACCOUNT.finditer(text)]


def pii_middleware() -> list:
    return [
        PIIMiddleware("credit_card", strategy="mask", apply_to_input=True, apply_to_tool_results=True),
        PIIMiddleware("account_number", detector=account_detector, strategy="hash", apply_to_input=True, apply_to_tool_results=True),
    ]


SAFE_FALLBACK = "I'm sorry, I can't share that answer. A colleague will follow up with you securely."


def validate_output(answer: str, *, needs_citation: bool) -> tuple[str, list[str]]:
    issues = []
    if ACCOUNT.search(answer):
        issues.append("full account number")
    if CARD.search(answer):
        issues.append("full card number")
    if PROMISES.search(answer):
        issues.append("forbidden promise")
    if needs_citation and "(source:" not in answer:
        issues.append("policy answer without a source")
    if not issues:
        return answer, []
    if issues == ["policy answer without a source"]:
        return answer + " (Please check the bank's published terms; I could not cite a source.)", issues
    return SAFE_FALLBACK, issues
