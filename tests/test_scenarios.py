import pytest

from lcstack.scenarios import MODULES, load

NUMBERS = list(range(1, len(MODULES) + 1))


def test_twenty_five_sections():
    assert len(MODULES) == 25
    metas = [load(n).META for n in NUMBERS]
    assert [m.number for m in metas] == NUMBERS
    assert {m.domain for m in metas} == {"retail", "banking", "healthcare", "insurance", "mortgage"}


@pytest.mark.parametrize("n", NUMBERS)
def test_scenario_runs_and_is_deterministic(n):
    mod = load(n)
    first = mod.run()
    assert first and all(isinstance(line, str) for line in first)
    assert mod.run() == first, "scenario output must be deterministic so the docs can embed it"


@pytest.mark.parametrize("n", NUMBERS)
def test_scenario_has_readme_and_module(n):
    from pathlib import Path

    m = load(n).META
    assert Path(m.module).exists()
    assert Path(m.folder, "README.md").exists()
