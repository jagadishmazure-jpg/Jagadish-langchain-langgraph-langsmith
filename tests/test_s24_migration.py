from lcstack.legacy import fnol_bot
from lcstack.scenarios import s24_migration as m
from lcstack.scenarios.s25_import_map import OLD_SERVICE, lint_paths, lint_source


def test_create_agent_matches_legacy_agentexecutor():
    q, f = "Hail hit my roof and car last night, I want to report it. Policy FW-HO-2207.", "Which policy did I report on?"
    old, new = m.legacy_run(q, f), m.modern_run(q, f)
    for key in ("calls", "answer", "followup", "summary"):
        assert old[key] == new[key], key


def test_legacy_module_is_labelled():
    assert "LEGACY" in (fnol_bot.__doc__ or "").upper()


def test_import_lint_flags_pre_1_0_and_repo_is_clean():
    assert len(lint_source(OLD_SERVICE)) >= 4
    _, bad = lint_paths(["src/lcstack/capstone", "src/lcstack/core"])
    assert bad == 0
