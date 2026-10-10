"""05 Prompts and LCEL: compose runnables with the pipe; retry, fall back, fan out, bind tools.

Client: Ferrowind Insurance claim handlers write long notes. Leadership, the customer and the fraud
unit each need a different summary, the primary model endpoint is flaky, and the fraud unit wants
entity extraction run alongside the summary in one call.
"""

from __future__ import annotations

import re

from langchain.tools import tool
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableParallel

from lcstack.core.companies import INSURANCE
from lcstack.core.scripted import Intent, Playbook, Turn, scripted
from lcstack.scenarios import Meta

META = Meta(5, "Prompts and LCEL", "ChatPromptTemplate, prompt | model | parser, with_retry, with_fallbacks, RunnableParallel, bind_tools",
            f"{INSURANCE}: claim-note summaries per audience", "insurance", "prompts-lcel")  # fmt: skip

NOTE = ("Claim FW-20931. Insured reports water damage to kitchen after a dishwasher hose failed. Plumber invoice 1,240.00 "
        "attached. Contractor estimate 8,900.00 for cabinets and flooring. Second loss at this address in 14 months.")  # fmt: skip

STYLE = {
    "executives": lambda n: f"Water loss, est. {_money(n)[-1]} exposure; repeat loss at address - review recommended.",
    "the customer": lambda n: "We have your claim for the kitchen water damage and are reviewing the plumber and contractor documents.",
    "the fraud unit": lambda n: f"Repeat water loss within 14 months; amounts {', '.join(_money(n))}; verify hose failure with the plumber.",
}


def _money(text: str) -> list[str]:
    return re.findall(r"\d{1,3}(?:,\d{3})*\.\d{2}", text)


def _summary(t: Turn) -> str:
    aud = re.search(r"for (.+?)\.", t.system)
    return STYLE.get(aud.group(1) if aud else "", lambda n: "Summary unavailable for this audience.")(t.last_human)


PLAYBOOK = Playbook(intents=[
    Intent("flag", lambda t: "fraud indicators" in t.system, answer=lambda t: "repeat_loss" if "Second loss" in t.last_human else "none"),
    Intent("lookup", r"look up", steps=[lambda t: ("get_policy", {"claim_id": "FW-20931"})], answer=lambda t: t.results.get("get_policy", "")),
    Intent("summary", r".", answer=_summary),
])  # fmt: skip

prompt = ChatPromptTemplate.from_messages([("system", "Summarize for {audience}. Plain words, one sentence."), ("human", "{text}")])


@tool
def get_policy(claim_id: str) -> str:
    """Look up the policy attached to a claim."""
    return f"{claim_id}: homeowners policy HO-3, deductible 1,000.00, water damage covered."


def run() -> list[str]:
    out = [f"{INSURANCE} - claim note summaries with LCEL", ""]
    model = scripted(PLAYBOOK, name="primary")
    chain = prompt | model | StrOutputParser()
    out.append(f"chain: {' | '.join(type(s).__name__ for s in chain.steps)}")
    results = chain.batch([{"audience": a, "text": NOTE} for a in STYLE])
    out += [f"  {a:<15} {r}" for a, r in zip(STYLE, results, strict=True)]

    flaky = scripted(PLAYBOOK, name="flaky-primary", fail_times=1)
    retried = (prompt | flaky.with_retry(stop_after_attempt=3, wait_exponential_jitter=False) | StrOutputParser()).invoke(
        {"audience": "executives", "text": NOTE}
    )
    out += ["", f"with_retry: first call timed out, second succeeded after {flaky.calls} calls -> {retried}"]

    down = scripted(PLAYBOOK, name="primary-down", fail_times=99)
    backup = scripted(PLAYBOOK, name="backup-region")
    fb_chain = prompt | down.with_fallbacks([backup]) | StrOutputParser()
    fb = fb_chain.invoke({"audience": "the customer", "text": NOTE})
    out.append(f"with_fallbacks: primary failed ({down.calls} call), backup answered ({backup.calls} call) -> {fb}")

    flags = ChatPromptTemplate.from_messages([("system", "List fraud indicators."), ("human", "{text}")]) | model | StrOutputParser()
    fan = RunnableParallel(summary=chain, fraud_flags=flags, amounts=RunnableLambda(lambda x: _money(x["text"])))
    par = fan.invoke({"audience": "the fraud unit", "text": NOTE})
    out += ["", "RunnableParallel (one input, three branches):"] + [f"  {k}: {v}" for k, v in par.items()]

    with_tools = model.bind_tools([get_policy])
    msg = with_tools.invoke("Please look up the policy for FW-20931")
    out += ["", f"bind_tools -> the model asks for a tool: {[(tc['name'], tc['args']) for tc in msg.tool_calls]}"]
    return out
