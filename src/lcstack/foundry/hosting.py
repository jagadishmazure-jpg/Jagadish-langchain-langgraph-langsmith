"""Responses and Invocations hosts for a compiled LangGraph graph.

``ResponsesHostServer`` and ``InvocationsHostServer`` follow the call shape described for
``langchain_azure_ai.agents.hosting``: pass a compiled graph, accept a protocol request, return
a protocol response. The classes in that package start an HTTP server and need Foundry. These
stand-ins run the graph in-process. ``run`` refuses to bind a port.

Two history rules, matching the hosting article:

* A graph **with** a checkpointer is sent only the new user message. The conversation id is the
  LangGraph thread. ``store: false`` is rejected, as in ``langchain-azure-ai`` 1.3.0.
* A graph **without** a checkpointer is sent the prior Responses transcript plus the new message.
  The host's conversation store is that transcript. It is not a checkpoint of the graph.

Interrupts become a ``function_call`` named ``__hosted_agent_adapter_interrupt__`` and an
``mcp_approval_request`` with ``server_label`` ``langgraph``. An ``mcp_approval_response`` resumes
LangChain human-in-the-loop middleware with ``{"decisions": [...]}``. For any other ``interrupt()``
value, approval resumes with that value and rejection does not resume the graph.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command

from lcstack.core.scripted import text_of
from lcstack.foundry.trace import FoundryTraceHook

STORE_FALSE = "a checkpointed graph must omit store or set it to true"
INTERRUPT_TOOL = "__hosted_agent_adapter_interrupt__"


class HostError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def counter_graph(checkpointer=None):
    """Small graph that reports how many user turns are in state. Used to show what the host sent."""

    def count(state: MessagesState) -> dict:
        humans = [message for message in state["messages"] if getattr(message, "type", None) == "human"]
        last = text_of(humans[-1]) if humans else ""
        return {"messages": [AIMessage(f"turns={len(humans)} last={last}")]}

    graph = StateGraph(MessagesState)
    graph.add_node("count", count)
    graph.add_edge(START, "count")
    graph.add_edge("count", END)
    return graph.compile(checkpointer=checkpointer, name="counter")


def _jsonable(value: Any) -> str:
    try:
        return json.dumps(value)
    except TypeError:
        return json.dumps(value, default=str)


def _interrupt_value(item: Any) -> Any:
    if hasattr(item, "value"):
        return item.value
    if isinstance(item, dict) and "value" in item:
        return item["value"]
    return item


def _assistant_text(result: dict) -> str:
    for message in reversed(result.get("messages") or []):
        if isinstance(message, AIMessage) and not message.tool_calls:
            return text_of(message)
    return ""


def _text_from_input(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                content = item.get("content", item.get("text", ""))
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    parts.extend(block.get("text", "") if isinstance(block, dict) else str(block) for block in content)
        return "\n".join(part for part in parts if part)
    raise HostError(400, "input must be a string or a list of items")


@dataclass
class _Turn:
    response_id: str
    conversation_id: str
    caller_id: str
    session_id: str
    checkpoint_id: str | None = None
    pending: dict | None = None
    settled: str | None = None


@dataclass
class _Conversation:
    conversation_id: str
    caller_id: str
    session_id: str
    messages: list[dict] = field(default_factory=list)


class ResponsesHostServer:
    """In-process stand-in for ``langchain_azure_ai.agents.hosting.ResponsesHostServer``."""

    def __init__(
        self,
        agent,
        *,
        enable_response_branching: bool = False,
        trace: FoundryTraceHook | None = None,
        context_for: Callable[[str], Any] | None = None,
        name: str = "agent",
    ) -> None:
        self.graph = agent
        self.enable_response_branching = enable_response_branching
        self.trace = trace if trace is not None else FoundryTraceHook()
        self.context_for = context_for
        self.name = name
        self._counts = {"resp": 0, "conv": 0, "sess": 0}
        self._turns: dict[str, _Turn] = {}
        self._conversations: dict[str, _Conversation] = {}
        self._heads: dict[str, str] = {}

    @property
    def _checkpointed(self) -> bool:
        return getattr(self.graph, "checkpointer", None) is not None

    @property
    def history_source(self) -> str:
        return "checkpointer" if self._checkpointed else "responses"

    def run(self, port: int = 8088) -> None:
        """The live class binds HTTP here. This stand-in never does."""
        raise RuntimeError(
            f"offline stand-in: not binding :{port}. Call handle_create(). The Azure class is langchain_azure_ai.agents.hosting.ResponsesHostServer."
        )

    def handle_create(self, body: dict, *, caller_id: str, agent_session_id: str | None = None) -> dict:
        """Handle one Responses request. ``caller_id`` is the platform identity, never a field of ``body``."""
        try:
            return self._create(body, caller_id=caller_id, agent_session_id=agent_session_id)
        except HostError as exc:
            return self._failed(exc.status, exc.message)
        except Exception as exc:
            return self._failed(500, f"{type(exc).__name__}: {exc}")

    def stream_events(self, body: dict, *, caller_id: str, agent_session_id: str | None = None) -> list[dict]:
        """Responses server-sent events for one request: created, output deltas, completed."""
        response = self.handle_create(body, caller_id=caller_id, agent_session_id=agent_session_id)
        events = [{"type": "response.created", "response": {"id": response["id"]}}]
        text = response.get("output_text") or ""
        parts = re.findall(r"\S+\s*", text)
        joined = "".join(parts)
        if joined != text:
            parts.append(text[len(joined) :])
        events.extend({"type": "response.output_text.delta", "delta": part} for part in parts)
        events.append({"type": "response.completed", "response": response})
        return events

    def build_input(self, text: str, prior_messages: list[dict]) -> Any:
        """Map protocol text onto graph state. Override for a custom state schema."""
        return {"messages": [*prior_messages, {"role": "user", "content": text}]}

    def _alloc(self, kind: str, prefix: str) -> str:
        self._counts[kind] += 1
        return f"{prefix}-{self._counts[kind]:04d}"

    def _failed(self, status: int, message: str) -> dict:
        return {
            "id": None,
            "object": "response",
            "status": "failed",
            "status_code": status,
            "conversation": None,
            "agent_session_id": None,
            "output": [],
            "output_text": "",
            "error": {"message": message},
            "hosted": {"history_source": self.history_source, "graph": self.name, "status_code": status},
        }

    def _create(self, body: dict, *, caller_id: str, agent_session_id: str | None) -> dict:
        if self._checkpointed and body.get("store") is False:
            raise HostError(400, STORE_FALSE)
        resume_item = self._resume_item(body)
        if resume_item is not None:
            return self._resume(body, resume_item, caller_id=caller_id, agent_session_id=agent_session_id)
        conversation, previous = self._resolve(body, caller_id=caller_id, agent_session_id=agent_session_id)
        if previous and previous.pending:
            raise HostError(400, "interrupt pending; send mcp_approval_response or function_call_output")
        text = _text_from_input(body.get("input", ""))
        if text == "":
            raise HostError(400, "input is empty")
        prior = [] if self._checkpointed else [dict(message) for message in conversation.messages]
        result, checkpoint_id = self._invoke(self.build_input(text, prior), previous, caller_id=caller_id, resume=False, conversation=conversation)
        response = self._finish(conversation, result, checkpoint_id, parent=previous)
        if not self._checkpointed and body.get("store") is not False:
            conversation.messages.append({"role": "user", "content": text})
            if response["output_text"]:
                conversation.messages.append({"role": "assistant", "content": response["output_text"]})
        elif not self._checkpointed:
            # One-shot: the response is returned and then forgotten, including its id.
            self._turns.pop(response["id"], None)
            self._conversations.pop(conversation.conversation_id, None)
            self._heads.pop(conversation.conversation_id, None)
        return response

    def _resume_item(self, body: dict) -> dict | None:
        value = body.get("input")
        if not isinstance(value, list):
            return None
        resume_types = {"function_call_output", "mcp_approval_response"}
        chosen = [item for item in value if isinstance(item, dict) and item.get("type") in resume_types]
        other = [item for item in value if not (isinstance(item, dict) and item.get("type") in resume_types)]
        if chosen and other:
            raise HostError(400, "resume input cannot be mixed with a new user message")
        if len(chosen) > 1:
            raise HostError(400, "send one resume item")
        return chosen[0] if chosen else None

    def _resume(self, body: dict, item: dict, *, caller_id: str, agent_session_id: str | None) -> dict:
        target = self._pending_turn(caller_id, item, self._previous_for_resume(body, caller_id))
        conversation = self._conversations[target.conversation_id]
        self._check_session(conversation, body, agent_session_id)
        if not self.enable_response_branching and self._heads.get(conversation.conversation_id) != target.response_id:
            raise HostError(400, "response branching is disabled")
        command = self._command_for(item, target.pending)
        if command is None:
            target.settled = "rejected"
            target.pending = None
            return self._envelope(
                target,
                status="failed",
                output=[],
                output_text="",
                error={"message": "interrupt rejected; graph was not resumed"},
            )
        result, checkpoint_id = self._invoke(command, target, caller_id=caller_id, resume=True)
        return self._finish(conversation, result, checkpoint_id, parent=target)

    def _previous_for_resume(self, body: dict, caller_id: str) -> _Turn | None:
        previous_id = body.get("previous_response_id")
        if not previous_id:
            return None
        previous = self._turns.get(previous_id)
        if previous is None:
            raise HostError(400, "unknown previous_response_id")
        if previous.caller_id != caller_id:
            raise HostError(400, "response belongs to another caller")
        return previous

    def _check_session(self, conversation: _Conversation, body: dict, agent_session_id: str | None) -> None:
        requested = agent_session_id if agent_session_id is not None else body.get("agent_session_id")
        if requested not in (None, conversation.session_id):
            raise HostError(400, "session does not match conversation")

    def _resolve(self, body: dict, *, caller_id: str, agent_session_id: str | None) -> tuple[_Conversation, _Turn | None]:
        previous_id = body.get("previous_response_id")
        requested_session = agent_session_id if agent_session_id is not None else body.get("agent_session_id")
        if previous_id:
            previous = self._turns.get(previous_id)
            if previous is None:
                raise HostError(400, "unknown previous_response_id")
            if previous.caller_id != caller_id:
                raise HostError(400, "response belongs to another caller")
            conversation = self._conversations[previous.conversation_id]
            if body.get("conversation") not in (None, conversation.conversation_id):
                raise HostError(400, "conversation does not match previous_response_id")
            if not self.enable_response_branching and self._heads.get(conversation.conversation_id) != previous.response_id:
                raise HostError(400, "response branching is disabled")
            self._check_session(conversation, body, agent_session_id)
            return conversation, previous
        if body.get("conversation"):
            conversation = self._conversations.get(body["conversation"])
            if conversation is None or conversation.caller_id != caller_id:
                raise HostError(400, "unknown conversation")
            self._check_session(conversation, body, agent_session_id)
            head = self._turns[self._heads[conversation.conversation_id]]
            return conversation, head
        session_id = requested_session or self._alloc("sess", "sess")
        conversation = _Conversation(self._alloc("conv", "conv"), caller_id, session_id)
        self._conversations[conversation.conversation_id] = conversation
        return conversation, None

    def _pending_turn(self, caller_id: str, item: dict, previous: _Turn | None) -> _Turn:
        if previous is not None:
            turn = previous
        else:
            matches = [
                turn
                for turn in self._turns.values()
                if turn.caller_id == caller_id
                and turn.pending
                and (
                    (item.get("call_id") and turn.pending["call_id"] == item.get("call_id"))
                    or (item.get("approval_request_id") and turn.pending["approval_id"] == item.get("approval_request_id"))
                )
            ]
            if len(matches) != 1:
                raise HostError(400, "resume item does not match a pending interrupt")
            turn = matches[0]
        if turn.settled:
            raise HostError(400, "interrupt already settled")
        if not turn.pending:
            raise HostError(400, "response has no pending interrupt")
        if item["type"] == "function_call_output" and item.get("call_id") != turn.pending["call_id"]:
            raise HostError(400, "call_id does not match the interrupt")
        if item["type"] == "mcp_approval_response" and item.get("approval_request_id") != turn.pending["approval_id"]:
            raise HostError(400, "approval_request_id does not match the interrupt")
        if turn.caller_id != caller_id:
            raise HostError(400, "response belongs to another caller")
        return turn

    def _command_for(self, item: dict, pending: dict) -> Command | None:
        if item["type"] == "mcp_approval_response":
            approve = item.get("approve")
            if not isinstance(approve, bool):
                raise HostError(400, "mcp_approval_response requires approve true or false")
            if pending["hitl"]:
                decision = {"type": "approve"} if approve else {"type": "reject"}
                return Command(resume={"decisions": [decision for _ in range(pending["n_actions"])]})
            if not approve:
                return None
            return Command(resume=pending["value"])
        raw = item.get("output", "")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw) if raw else ""
            except json.JSONDecodeError:
                parsed = raw
        else:
            parsed = raw
        if isinstance(parsed, dict) and parsed and set(parsed).issubset({"resume", "update", "goto"}):
            return Command(**parsed)
        return Command(resume=parsed)

    def _invoke(
        self, graph_input: Any, previous: _Turn | None, *, caller_id: str, resume: bool, conversation: _Conversation | None = None
    ) -> tuple[dict, str | None]:
        conversation_id = previous.conversation_id if previous else conversation.conversation_id
        thread_id = f"{caller_id}:{conversation_id}"
        response_id = self._alloc("resp", "resp")
        recorder = self.trace.recorder()
        config: dict[str, Any] = {"callbacks": [recorder], "metadata": {"caller_id": caller_id, "graph": self.name}}
        if self._checkpointed:
            configurable: dict[str, str] = {"thread_id": thread_id}
            # A non-head previous_response_id is a fork. Resume of the head uses the thread as it stands.
            if previous is not None and previous.checkpoint_id and self._heads.get(previous.conversation_id) != previous.response_id and not resume:
                configurable["checkpoint_id"] = previous.checkpoint_id
            config["configurable"] = configurable
        kwargs: dict[str, Any] = {}
        if self.context_for is not None:
            kwargs["context"] = self.context_for(caller_id)
        try:
            result = self.graph.invoke(graph_input, config, **kwargs)
        finally:
            self.trace.collect(recorder, response_id=response_id, caller_id=caller_id)
        checkpoint_id = None
        if self._checkpointed:
            snap = self.graph.get_state({"configurable": {"thread_id": thread_id}})
            checkpoint_id = (snap.config or {}).get("configurable", {}).get("checkpoint_id")
        result = dict(result)
        result["_response_id"] = response_id
        result["_thread_id"] = thread_id
        return result, checkpoint_id

    def _finish(self, conversation: _Conversation, result: dict, checkpoint_id: str | None, *, parent: _Turn | None) -> dict:
        interrupts = list(result.get("__interrupt__") or [])
        if len(interrupts) > 1:
            raise HostError(500, "multiple interrupts in one turn are not handled by this stand-in")
        response_id = result["_response_id"]
        output, pending = self._output_items(response_id, interrupts)
        text = "" if pending else _assistant_text(result)
        if text:
            output.insert(0, {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]})
        turn = _Turn(
            response_id=response_id,
            conversation_id=conversation.conversation_id,
            caller_id=conversation.caller_id,
            session_id=conversation.session_id,
            checkpoint_id=checkpoint_id,
            pending=pending,
        )
        self._turns[response_id] = turn
        self._heads[conversation.conversation_id] = response_id
        if parent and parent.pending:
            parent.settled = "resumed"
            parent.pending = None
        return self._envelope(
            turn, status="incomplete" if pending else "completed", output=output, output_text=text, error=None, thread_id=result["_thread_id"]
        )

    def _output_items(self, response_id: str, interrupts: list) -> tuple[list[dict], dict | None]:
        if not interrupts:
            return [], None
        value = _interrupt_value(interrupts[0])
        hitl = isinstance(value, dict) and "action_requests" in value
        actions = value.get("action_requests") or [] if hitl else []
        name = actions[0].get("name", "interrupt") if actions else "interrupt"
        call_id = f"call-{response_id}"
        approval_id = f"apr-{response_id}"
        items = [
            {"type": "function_call", "name": INTERRUPT_TOOL, "call_id": call_id, "arguments": _jsonable(value)},
            {
                "type": "mcp_approval_request",
                "id": approval_id,
                "server_label": "langgraph",
                "name": name,
                "arguments": _jsonable(actions[0].get("args") if actions else value),
            },
        ]
        pending = {"call_id": call_id, "approval_id": approval_id, "value": value, "hitl": hitl, "n_actions": max(1, len(actions))}
        return items, pending

    def _envelope(self, turn: _Turn, *, status: str, output: list, output_text: str, error: dict | None, thread_id: str | None = None) -> dict:
        thread = thread_id or f"{turn.caller_id}:{turn.conversation_id}"
        return {
            "id": turn.response_id,
            "object": "response",
            "status": status,
            "status_code": 200,
            "conversation": turn.conversation_id,
            "agent_session_id": turn.session_id,
            "output": output,
            "output_text": output_text,
            "error": error,
            "hosted": {
                "status_code": 200,
                "graph_thread_id": thread,
                "checkpoint_id": turn.checkpoint_id,
                "history_source": self.history_source,
                "graph": self.name,
                "content_recording": self.trace.record_content,
            },
        }


class InvocationsHostServer:
    """In-process stand-in for ``InvocationsHostServer``.

    The platform does not store the transcript. A checkpointer keyed by caller and session is how
    later calls on the same sandbox keep graph state. A different caller does not share that state.
    """

    def __init__(self, agent, *, context_for: Callable[[str], Any] | None = None, trace: FoundryTraceHook | None = None, name: str = "agent") -> None:
        self.graph = agent
        self.context_for = context_for
        self.trace = trace if trace is not None else FoundryTraceHook()
        self.name = name
        self._sessions = 0

    def run(self, port: int = 8088) -> None:
        raise RuntimeError(
            f"offline stand-in: not binding :{port}. Call handle(). The Azure class is langchain_azure_ai.agents.hosting.InvocationsHostServer."
        )

    def parse_request(self, body: dict) -> tuple[str, bool]:
        """Default body is ``{"message": "...", "stream": false}``. Override for a custom schema."""
        if "message" not in body:
            raise HostError(400, "message is required")
        return str(body["message"]), bool(body.get("stream", False))

    def handle(self, body: dict, *, agent_session_id: str | None = None, caller_id: str = "anonymous") -> dict:
        try:
            message, _stream = self.parse_request(body)
            session_id = agent_session_id or self._new_session()
            text, session_id = self._run(message, session_id=session_id, caller_id=caller_id)
            return {"response": text, "headers": {"x-agent-session-id": session_id}, "status_code": 200, "error": None}
        except HostError as exc:
            return {"response": "", "headers": {}, "status_code": exc.status, "error": {"message": exc.message}}
        except Exception as exc:
            return {"response": "", "headers": {}, "status_code": 500, "error": {"message": f"{type(exc).__name__}: {exc}"}}

    def stream(self, body: dict, *, agent_session_id: str | None = None, caller_id: str = "anonymous") -> list[dict]:
        """Token events followed by a terminal ``done`` event, as the Invocations host describes them."""
        result = self.handle(body, agent_session_id=agent_session_id, caller_id=caller_id)
        events = [{"event": "token", "data": {"token": part}} for part in re.findall(r"\S+\s*", result["response"])]
        events.append({"event": "done", "data": {}})
        return events

    def _new_session(self) -> str:
        self._sessions += 1
        return f"sess-{self._sessions:04d}"

    def _run(self, message: str, *, session_id: str, caller_id: str) -> tuple[str, str]:
        recorder = self.trace.recorder()
        config: dict[str, Any] = {"callbacks": [recorder]}
        if getattr(self.graph, "checkpointer", None) is not None:
            config["configurable"] = {"thread_id": f"{caller_id}:{session_id}"}
        kwargs = {"context": self.context_for(caller_id)} if self.context_for is not None else {}
        try:
            result = self.graph.invoke({"messages": [{"role": "user", "content": message}]}, config, **kwargs)
        finally:
            self.trace.collect(recorder, response_id=session_id, caller_id=caller_id)
        return _assistant_text(dict(result)), session_id
