"""03 Install and Chat Models: one interface for every provider; invoke, stream, batch and async.

Client: Halsey Vale Health's patient portal answers short administrative questions (parking, visiting
hours, how to request records). The same model object serves the chat window (stream), the nightly
FAQ refresh (batch) and the API gateway (async, many requests in flight).
"""

from __future__ import annotations

import asyncio
import importlib.util

from lcstack.core.companies import HEALTHCARE
from lcstack.core.models import chat_model
from lcstack.core.scripted import Intent, Playbook
from lcstack.scenarios import Meta

META = Meta(3, "Install and Chat Models", "init_chat_model provider strings; invoke, stream, batch, ainvoke/abatch; usage metadata",
            f"{HEALTHCARE}: patient-portal FAQ answers", "healthcare", "chat-models")  # fmt: skip

FAQ = {
    r"park": "Visitor parking is in the North garage; the first two hours are free with a validated ticket.",
    r"visit": "General wards welcome visitors from 9:00 to 20:00, two at a time per bedside.",
    r"record": "Request your records through the portal's Records tab; most requests are fulfilled in five working days.",
    r"pharmac": "The outpatient pharmacy on level 1 is open 8:00 to 18:00 on weekdays.",
}
PLAYBOOK = Playbook(
    intents=[Intent(k, k, answer=v) for k, v in FAQ.items()],
    fallback="Please call the front desk for that question; I can only answer portal and visiting questions.",
)

# provider prefix -> the integration package that init_chat_model loads for it
PROVIDERS = {
    "azure_openai": "langchain_openai",
    "openai": "langchain_openai",
    "anthropic": "langchain_anthropic",
    "google_genai": "langchain_google_genai",
    "bedrock_converse": "langchain_aws",
    "ollama": "langchain_ollama",
}


def provider_table() -> list[tuple[str, str, bool]]:
    return [(p, pkg, importlib.util.find_spec(pkg) is not None) for p, pkg in PROVIDERS.items()]


async def _async_demo(m) -> tuple[list[str], list[str]]:
    qs = ["Where do I park?", "When can I visit?", "How do I get my records?"]
    gathered = await asyncio.gather(*(m.ainvoke(q) for q in qs))
    batched = await m.abatch(qs)
    return [g.content for g in gathered], [b.content for b in batched]


def run() -> list[str]:
    m = chat_model(PLAYBOOK, name="portal-faq")
    out = [f"{HEALTHCARE} - patient-portal FAQ through one chat-model interface", ""]
    out.append('init_chat_model("<provider>:<model>") picks the integration package from the prefix:')
    for p, pkg, ok in provider_table():
        out.append(f"  {p + ':...':<20} -> {pkg:<24} {'installed' if ok else 'not installed (pip install it to use)'}")
    r = m.invoke("Where should visitors park?")
    out += ["", f"invoke : {r.content}", f"         usage_metadata (simulated count): {r.usage_metadata}"]
    chunks = list(m.stream("What are the visiting hours?"))
    out.append(f"stream : {len(chunks)} chunks -> {''.join(c.content for c in chunks)!r}")
    batch = m.batch(["Pharmacy hours?", "How do I request my records?", "Can I bring my dog?"])
    out.append("batch  :")
    out += [f"  - {b.content}" for b in batch]
    gathered, abatched = asyncio.run(_async_demo(m))
    out.append(
        f"async  : asyncio.gather over 3 ainvoke calls -> {len(gathered)} answers; abatch -> {len(abatched)} answers; identical: {gathered == abatched}"
    )
    out.append(f"total model calls: {m.calls}")
    return out
