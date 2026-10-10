"""06 Structured Output: typed, validated results with Pydantic, from a model and from an agent.

Client: Ferrowind Insurance first-notice-of-loss (FNOL) triage. Every new claim must come out as a
``ClaimTriage`` record (line of business, severity 1-5, fraud signal, next action) that the claims
system can store without a human retyping it. Invalid output must never reach the queue.
"""

from __future__ import annotations

import re
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.tools import tool
from pydantic import BaseModel, Field, ValidationError

from lcstack.core.companies import INSURANCE
from lcstack.core.scripted import Intent, Playbook, ToolMessage, Turn, scripted
from lcstack.scenarios import Meta

META = Meta(6, "Structured Output", "with_structured_output(Pydantic), include_raw, create_agent(response_format=ToolStrategy) with error retry",
            f"{INSURANCE}: FNOL claim triage into a typed record", "insurance", "structured-output")  # fmt: skip


class ClaimTriage(BaseModel):
    """Triage record for a first notice of loss."""

    line: Literal["auto", "property", "liability", "travel"]
    severity: int = Field(ge=1, le=5, description="1 = minor, 5 = catastrophic or bodily injury")
    fraud_signal: bool = Field(description="True when the notice contains a known fraud indicator")
    next_action: Literal["fast_track", "adjuster_visit", "special_investigations", "medical_review"]
    summary: str = Field(max_length=160)


FNOL = [
    "Rear-ended at a red light on the ring road, bumper cracked, nobody hurt.",
    "Burst pipe flooded the basement overnight, furniture and boiler ruined.",
    "Customer slipped on a wet floor in our client's shop and broke her wrist, ambulance called.",
    "Luggage lost on a connecting flight, contents listed at 4,200.00, no receipts, third claim this year.",
    "Car fire in the driveway at 3am, policy started 9 days ago.",
]


def triage_rules(text: str) -> dict:
    t = text.lower()
    line = ("auto" if re.search(r"car|bumper|rear-ended|vehicle", t) else "travel" if re.search(r"luggage|flight", t)
            else "liability" if re.search(r"slipped|customer|injur", t) else "property")  # fmt: skip
    injury = bool(re.search(r"broke|ambulance|injur|hurt(?! nobody)", t)) and "nobody hurt" not in t
    fraud = bool(re.search(r"no receipts|third claim|started \d+ days ago|3am", t))
    severity = 5 if injury else 4 if re.search(r"fire|flood", t) else 3 if fraud else 2
    action = "special_investigations" if fraud else "medical_review" if injury else "adjuster_visit" if severity >= 4 else "fast_track"
    return {"line": line, "severity": severity, "fraud_signal": fraud, "next_action": action, "summary": text[:120]}


def _extract(turn: Turn) -> dict:
    return triage_rules(turn.last_human)


def _sloppy_then_fixed(turn: Turn) -> dict:
    """First attempt overshoots severity (10); after the validation error comes back, it corrects itself."""
    data = triage_rules(turn.last_human)
    errored = any(isinstance(m, ToolMessage) and "error" in str(m.content).lower() for m in turn.messages)
    return data if errored else {**data, "severity": 10}


@tool
def policy_status(claim_text: str) -> str:
    """Check whether the policy behind a claim is active and when it started."""
    days = re.search(r"started (\d+) days ago", claim_text)
    return f"active; inception {days.group(1)} days ago" if days else "active; inception over 1 year ago"


def run() -> list[str]:
    out = [f"{INSURANCE} - FNOL triage into ClaimTriage", ""]
    model = scripted(Playbook(extractors={"ClaimTriage": _extract}), name="triage")
    triage = model.with_structured_output(ClaimTriage)
    out.append(f"{'line':<10} {'sev':>3} {'fraud':<6} {'next_action':<23} notice")
    for text in FNOL:
        t = triage.invoke(text)
        out.append(f"{t.line:<10} {t.severity:>3} {t.fraud_signal!s:<6} {t.next_action:<23} {text[:52]}")

    sloppy = scripted(Playbook(extractors={"ClaimTriage": lambda t: {**triage_rules(t.last_human), "severity": 10}}), name="sloppy")
    raw = sloppy.with_structured_output(ClaimTriage, include_raw=True).invoke(FNOL[0])
    err = raw["parsing_error"]
    first = err.errors()[0] if isinstance(err, ValidationError) else {}
    out += ["", f"include_raw on a bad answer: parsed={raw['parsed']}, error={type(err).__name__} at {first.get('loc')} ({first.get('msg')})"]

    pb = Playbook(
        intents=[Intent("check", r".", steps=[lambda t: ("policy_status", {"claim_text": t.last_human})])],
        extractors={"ClaimTriage": _sloppy_then_fixed},
    )
    agent_model = scripted(pb, name="triage-agent")
    agent = create_agent(agent_model, [policy_status], response_format=ToolStrategy(ClaimTriage, handle_errors=True))
    res = agent.invoke({"messages": [{"role": "user", "content": FNOL[4]}]})
    tm = [m for m in res["messages"] if isinstance(m, ToolMessage)]
    out += ["", "create_agent(response_format=ToolStrategy(ClaimTriage, handle_errors=True)):"]
    for m in tm:
        out.append(f"  tool {m.name:<12} -> {str(m.content).splitlines()[0][:96]}")
    sr = res["structured_response"]
    out.append(f"  structured_response: line={sr.line} severity={sr.severity} fraud={sr.fraud_signal} next={sr.next_action}")
    out.append(f"  model calls: {agent_model.calls} (tool call, invalid answer, corrected answer)")
    return out
