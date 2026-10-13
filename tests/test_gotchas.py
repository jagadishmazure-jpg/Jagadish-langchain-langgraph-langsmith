"""Each gotcha is shown failing first, then fixed."""

from lcstack.scenarios import s23_gotchas as g


def test_g1_uncompiled_builder_has_no_invoke():
    assert g.g1_broken().startswith("AttributeError")
    assert g.g1_fixed().startswith("checks=")


def test_g2_thread_id_is_the_memory():
    assert g.g2_turns(same_thread=False) != g.g2_turns(same_thread=True)


def test_g3_recursion_limit_and_exit_edge():
    assert "GraphRecursionError" in g.g3_broken()
    assert "then exit" in g.g3_fixed()


def test_g4_reducer_accumulates_across_runs():
    assert g.g4_run(reset=False) != g.g4_run(reset=True)


def test_g5_command_plus_static_edge_runs_both():
    assert g.g5_run(static_edge_too=True) != g.g5_run(static_edge_too=False)


def test_g6_side_effect_before_interrupt_repeats():
    assert g.g6_run(idempotent=False) != g.g6_run(idempotent=True)
    assert "1 time" in g.g6_run(idempotent=True)


def test_g7_checkpoint_types_need_allowlist():
    # langgraph warns once per process per type, so each variant runs in a fresh interpreter
    import subprocess
    import sys

    def fresh(flag):
        code = f"from lcstack.scenarios.s23_gotchas import g7_run; print(g7_run({flag}))"
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()

    assert fresh(False).endswith("warning logged=True")
    assert fresh(True).endswith("warning logged=False")
