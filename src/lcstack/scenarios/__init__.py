"""The 25 scenarios, one per section of the cheat sheet. Each module exposes ``META`` and ``run() -> list[str]``."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType


@dataclass(frozen=True)
class Meta:
    number: int
    section: str  # the cheat-sheet section title
    concept: str  # what the scenario demonstrates
    client: str  # fictional client and use case
    domain: str
    slug: str

    @property
    def folder(self) -> str:
        return f"scenarios/{self.number:02d}-{self.slug}"

    @property
    def module(self) -> str:
        return f"src/lcstack/scenarios/s{self.number:02d}_{self.slug.replace('-', '_')}.py"


MODULES = [
    "s01_ecosystem",
    "s02_which_layer",
    "s03_chat_models",
    "s04_messages",
    "s05_prompts_lcel",
    "s06_structured_output",
    "s07_tools",
    "s08_create_agent",
    "s09_middleware",
    "s10_retrieval",
    "s11_mental_model",
    "s12_state_reducers",
    "s13_react_by_hand",
    "s14_control_flow",
    "s15_persistence",
    "s16_human_in_the_loop",
    "s17_long_term_memory",
    "s18_streaming",
    "s19_multi_agent",
    "s20_functional_api",
    "s21_tracing",
    "s22_deploying",
    "s23_gotchas",
    "s24_migration",
    "s25_import_map",
]


def load(number: int) -> ModuleType:
    return importlib.import_module(f"lcstack.scenarios.{MODULES[number - 1]}")


def all_meta() -> list[Meta]:
    return [load(i).META for i in range(1, len(MODULES) + 1)]
