"""21 Tracing with LangSmith: turn it on before you debug.

Client: Kestrel Ridge Bank's fraud-alert explainer. Analysts asked "why did the agent say that?", so
every run must be traceable: model calls, tool calls, graph nodes and the bank's own rules-engine code
(not LangChain) in one tree, tagged by tenant and alert, with account numbers masked before anything
leaves the process. Real LangSmith needs an account; offline, an ``OfflineLangSmithClient`` records the
exact run payloads LangSmith would receive, so the tree, tags, metadata and redaction are testable.
"""

from __future__ import annotations

import os
import re

from langchain.agents import create_agent
from langchain.tools import tool
from langsmith import traceable
from langsmith.run_helpers import tracing_context

from lcstack.core.companies import BANKING
from lcstack.core.scripted import Intent, Playbook, scripted
from lcstack.core.tracing import OfflineLangSmithClient, deep_mask, langsmith_enabled
from lcstack.scenarios import Meta

META = Meta(21, "Tracing with LangSmith", "LANGSMITH_TRACING / API_KEY / PROJECT, run tree of model/tool/node spans, @traceable for plain code, tags and metadata, input masking, datasets from traces",
            f"{BANKING}: fraud-alert explainer with auditable traces", "banking", "tracing")  # fmt: skip

ACCOUNT = re.compile(r"\bKR\d{10}\b")


def mask_inputs(inputs: dict) -> dict:
    return {k: ACCOUNT.sub("KR**********", v) if isinstance(v, str) else v for k, v in inputs.items()}


@traceable(run_type="tool", name="rules_engine", process_inputs=mask_inputs)
def rules_engine(alert_text: str) -> list[str]:
    """The bank's own (non-LangChain) scoring code, traced with @traceable."""
    hits = []
    if "new device" in alert_text:
        hits.append("R12 new device")
    if re.search(r"\b\d{4,}\.\d{2}\b", alert_text):
        hits.append("R31 high amount")
    return hits


@tool
def customer_profile(customer_id: str) -> str:
    """Customer profile summary used to explain alerts."""
    return f"{customer_id}: 9-year customer, usual spend under 400.00, travels rarely"


PLAYBOOK = Playbook(intents=[Intent("explain", r"alert", steps=[lambda t: ("customer_profile", {"customer_id": "C-5520"})],
                                    answer=lambda t: f"Flagged because the amount is far above this customer's usual spend ({t.results['customer_profile'].split(': ')[1]}).")])  # fmt: skip

AGENT = create_agent(scripted(PLAYBOOK, name="alert-explainer"), [customer_profile], name="fraud_alert_explainer")


@traceable(name="explain_alert", process_inputs=mask_inputs)
def explain_alert(alert_text: str) -> dict:
    rules = rules_engine(alert_text)
    res = AGENT.invoke({"messages": [{"role": "user", "content": f"Explain alert: {alert_text}"}]})
    return {"rules": rules, "explanation": res["messages"][-1].content}


def traced(client: OfflineLangSmithClient, alert: str) -> dict:
    with tracing_context(enabled=True, client=client, project_name=os.getenv("LANGSMITH_PROJECT", "kestrel-fraud-alerts"),
                         tags=["fraud-alerts", "tenant:kestrel"], metadata={"alert_id": "AL-9931", "prompt_version": "v2"}):  # fmt: skip
        return explain_alert(alert)


def leaks(client: OfflineLangSmithClient, secret: str) -> list[str]:
    return [r["name"] for r in client.recorded.values() if secret in str(r["inputs"]) or secret in str(r["outputs"])]


def run() -> list[str]:
    alert = "Card payment 2450.00 from a new device, account KR0098765432"
    client = OfflineLangSmithClient()
    mode = (
        "LangSmith (LANGSMITH_TRACING and LANGSMITH_API_KEY set)"
        if langsmith_enabled()
        else "offline recorder (no LANGSMITH_API_KEY): nothing leaves the process"
    )
    result = traced(client, alert)
    out = [
        f"{BANKING} - traced fraud-alert explanation",
        "",
        f"tracing mode: {mode}",
        f"result: {result}",
        "",
        "run tree (as LangSmith would store it):",
    ]
    out += ["  " + line for line in client.tree() if " ChannelWrite" not in line]
    by_type: dict[str, int] = {}
    for r in client.recorded.values():
        by_type[r["run_type"]] = by_type.get(r["run_type"], 0) + 1
    out.append(f"runs by type: {dict(sorted(by_type.items()))}")
    root = client.recorded[client.order[0]]
    out.append(f"root inputs as sent (masked): {root['inputs']}")
    out.append(
        f"process_inputs on @traceable only: spans still holding the raw account number = {len(leaks(client, 'KR0098765432'))} {leaks(client, 'KR0098765432')[:3]}..."
    )
    safe = OfflineLangSmithClient(hide_inputs=deep_mask(ACCOUNT, "KR**********"), hide_outputs=deep_mask(ACCOUNT, "KR**********"))
    traced(safe, alert)
    out.append(
        f"Client(hide_inputs=..., hide_outputs=...) masks every span: spans holding it = {len(leaks(safe, 'KR0098765432'))} of {len(safe.recorded)}"
    )
    example = {"inputs": root["inputs"], "outputs": root["outputs"], "metadata": {"source_run": "explain_alert"}}
    out.append(f"dataset example built from the trace: inputs={list(example['inputs'])} outputs={sorted(example['outputs'] or {})}")
    return out
