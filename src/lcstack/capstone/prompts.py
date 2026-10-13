"""Prompt versioning: a local registry that mirrors LangSmith's prompt hub (name, versions, a production tag).

Each version is a text file; its SHA-256 (first 12 hex) is the commit hash recorded on every run's
metadata, so an evaluation or a trace always says exactly which prompt produced it. With a LangSmith
account, ``push_to_langsmith`` publishes the same versions with ``Client.push_prompt`` (not run in CI).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

DIR = Path(__file__).with_name("prompts")

# Behaviour flags the scripted model reads from the system prompt (a real model just reads the words).
CITE = "Cite the source document"
DATA_RULE = "never as instructions"
MASK_RULE = "last four digits"


@dataclass(frozen=True)
class PromptVersion:
    name: str
    version: str
    text: str
    note: str

    @property
    def sha(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:12]


def registry() -> dict:
    return json.loads((DIR / "registry.json").read_text())


def get_prompt(version: str | None = None) -> PromptVersion:
    reg = registry()
    v = version or reg["production"]
    meta = reg["versions"][v]
    return PromptVersion(reg["name"], v, (DIR / meta["file"]).read_text().strip(), meta["note"])


def all_versions() -> list[PromptVersion]:
    return [get_prompt(v) for v in registry()["versions"]]


def push_to_langsmith() -> list[str]:  # pragma: no cover - needs a LangSmith account
    from langchain_core.prompts import ChatPromptTemplate
    from langsmith import Client

    client, urls = Client(), []
    for p in all_versions():
        tmpl = ChatPromptTemplate.from_messages([("system", p.text), ("placeholder", "{messages}")])
        urls.append(client.push_prompt(p.name, object=tmpl, tags=[p.version] + (["production"] if p.version == registry()["production"] else [])))
    return urls
