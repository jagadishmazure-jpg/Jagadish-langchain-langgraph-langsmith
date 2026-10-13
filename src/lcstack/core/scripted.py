"""A deterministic chat model that behaves like a tool-calling LLM, so every scenario runs with no API key.

``ScriptedChatModel`` is a real ``BaseChatModel``: it supports ``invoke``/``stream``/``batch``/async,
``bind_tools``, ``with_structured_output`` and token streaming inside LangGraph. Instead of a neural
network it follows a ``Playbook``: a list of ``Intent`` rules matched against the latest user turn. Each
intent lists tool steps (emitted one model turn at a time, or several at once for parallel calls) and an
answer template that reads the tool results. That makes agent loops, routing, HITL and evaluations
reproducible bit for bit, and it means numbers produced with it measure the plumbing, retrieval and
guardrails, not an LLM's judgement. Swap in a real model with ``LCSTACK_MODEL`` (see ``models.py``).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict, PrivateAttr


def text_of(msg: BaseMessage) -> str:
    """Plain text of a message, flattening multimodal content blocks."""
    c = msg.content
    if isinstance(c, str):
        return c
    return " ".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in c)


def stable_id(*parts: Any) -> str:
    return "call_" + hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:10]


@dataclass
class Turn:
    """What the model sees on one call: the conversation, the bound tools and any forced tool choice."""

    messages: list[BaseMessage]
    tools: list[dict] = field(default_factory=list)
    tool_choice: Any = None

    @property
    def tool_names(self) -> list[str]:
        return [t["function"]["name"] for t in self.tools]

    @property
    def system(self) -> str:
        return "\n".join(text_of(m) for m in self.messages if isinstance(m, SystemMessage))

    @property
    def last_human(self) -> str:
        for m in reversed(self.messages):
            if isinstance(m, HumanMessage):
                return text_of(m)
        return ""

    def _since_human(self) -> list[BaseMessage]:
        out: list[BaseMessage] = []
        for m in reversed(self.messages):
            if isinstance(m, HumanMessage):
                break
            out.append(m)
        return list(reversed(out))

    @property
    def calls(self) -> list[dict]:
        """Tool calls already made since the latest user message."""
        return [tc for m in self._since_human() if isinstance(m, AIMessage) for tc in m.tool_calls]

    @property
    def results(self) -> dict[str, str]:
        """Tool name -> latest result text since the latest user message."""
        by_id = {tc["id"]: tc["name"] for tc in self.calls}
        out: dict[str, str] = {}
        for m in self._since_human():
            if isinstance(m, ToolMessage):
                out[by_id.get(m.tool_call_id, m.name or "?")] = text_of(m)
        return out

    def calls_names(self) -> list[str]:
        return [tc["name"] for tc in self.calls]

    def errored(self, name: str) -> bool:
        """True when the latest result of ``name`` in this turn was an error the model should react to."""
        res = self.results.get(name)
        return res is not None and res.lstrip().lower().startswith("error")

    def called(self, name: str, args: dict | None = None) -> bool:
        return any(tc["name"] == name and (args is None or tc["args"] == args) for tc in self.calls)


ToolStep = Callable[[Turn], "tuple[str, dict] | list[tuple[str, dict]] | None"]


@dataclass
class Intent:
    """One behaviour: when ``match`` fits the user turn, run ``steps`` (tool calls) then ``answer``."""

    name: str
    match: str | Callable[[Turn], bool]
    steps: list[ToolStep] = field(default_factory=list)
    answer: Callable[[Turn], str] | str = ""

    def matches(self, turn: Turn) -> bool:
        if callable(self.match):
            return bool(self.match(turn))
        return re.search(self.match, turn.last_human, re.I) is not None


@dataclass
class Playbook:
    """Ordered intents plus extractors for structured output (schema name -> function of the turn)."""

    intents: list[Intent] = field(default_factory=list)
    extractors: dict[str, Callable[[Turn], dict]] = field(default_factory=dict)
    fallback: Callable[[Turn], str] | str = "I can help with that. Could you give me a little more detail?"

    def respond(self, turn: Turn) -> AIMessage:
        # 1. forced tool choice (with_structured_output binds the schema with tool_choice="any")
        if turn.tool_choice and turn.tools and all(n in self.extractors for n in turn.tool_names):
            for name in turn.tool_names:
                if name in self.extractors:
                    return _call(name, self.extractors[name](turn))
        intent = next((i for i in self.intents if i.matches(turn)), None)
        if intent is not None:
            for step in intent.steps:
                planned = step(turn)
                if not planned:
                    continue
                batch = planned if isinstance(planned, list) else [planned]
                todo = [(n, a) for n, a in batch if n in turn.tool_names and not turn.called(n, a)]
                if todo:
                    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": stable_id(n, a, len(turn.calls))} for n, a in todo])
        # 2. agent structured output (create_agent response_format -> ToolStrategy exposes the schema as a tool)
        for name in turn.tool_names:
            if name in self.extractors and (not turn.called(name) or turn.errored(name)):
                return _call(name, self.extractors[name](turn))
        source = intent.answer if intent is not None else self.fallback
        return AIMessage(content=source(turn) if callable(source) else source)


def _call(name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": stable_id(name, args)}])


def count_tokens(text: str) -> int:
    """Rough, deterministic token count (about 0.75 words per token), labelled as simulated wherever shown."""
    return max(1, round(len(text.split()) / 0.75))


class ScriptedChatModel(BaseChatModel):
    """Deterministic, tool-calling chat model driven by a :class:`Playbook`.

    ``fail_times`` makes the first N calls raise ``TimeoutError`` (for retry and fallback demos).
    ``calls`` counts every invocation so tests can prove what ran.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    playbook: Playbook = Playbook()
    model_name: str = "scripted"
    fail_times: int = 0
    _calls: list[int] = PrivateAttr(default_factory=lambda: [0])
    _tools_seen: set[str] = PrivateAttr(default_factory=set)
    _inputs: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    @property
    def calls(self) -> int:
        return self._calls[0]

    @property
    def inputs(self) -> list[list[BaseMessage]]:
        """Exactly what the model received on each call (after middleware), for tests and audits."""
        return self._inputs

    @property
    def tools_seen(self) -> list[str]:
        """Every tool name this model was ever offered (shows how much a layer adds)."""
        return sorted(self._tools_seen)

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_name": self.model_name}

    def bind_tools(self, tools: Sequence[Any], *, tool_choice: Any = None, **kwargs: Any):
        formatted = [convert_to_openai_tool(t) for t in tools]
        return self.bind(tools=formatted, tool_choice=tool_choice, **kwargs)

    def _respond(self, messages: list[BaseMessage], **kwargs: Any) -> AIMessage:
        self._calls[0] += 1
        self._inputs.append(list(messages))
        if self._calls[0] <= self.fail_times:
            raise TimeoutError(f"{self.model_name}: simulated provider timeout (call {self._calls[0]})")
        turn = Turn(messages=list(messages), tools=kwargs.get("tools") or [], tool_choice=kwargs.get("tool_choice"))
        self._tools_seen.update(turn.tool_names)
        msg = self.playbook.respond(turn)
        prompt_tokens = sum(count_tokens(text_of(m)) for m in messages)
        out_text = msg.content if isinstance(msg.content, str) else ""
        out_tokens = count_tokens(out_text + json.dumps([tc["args"] for tc in msg.tool_calls]))
        msg.usage_metadata = {"input_tokens": prompt_tokens, "output_tokens": out_tokens, "total_tokens": prompt_tokens + out_tokens}
        msg.response_metadata = {"model_name": self.model_name, "finish_reason": "tool_calls" if msg.tool_calls else "stop"}
        return msg

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._respond(messages, **kwargs))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        msg = self._respond(messages, **kwargs)
        words = re.findall(r"\S+\s*", msg.content if isinstance(msg.content, str) else "")
        for w in words:
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=w))
            if run_manager:
                run_manager.on_llm_new_token(w, chunk=chunk)
            yield chunk
        last = AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": tc["name"], "args": json.dumps(tc["args"]), "id": tc["id"], "index": i} for i, tc in enumerate(msg.tool_calls)
            ],
            usage_metadata=msg.usage_metadata,
            response_metadata=msg.response_metadata,
            chunk_position="last",
        )
        yield ChatGenerationChunk(message=last)


def scripted(playbook: Playbook | None = None, *, name: str = "scripted", fail_times: int = 0) -> ScriptedChatModel:
    return ScriptedChatModel(playbook=playbook or Playbook(), model_name=name, fail_times=fail_times)
