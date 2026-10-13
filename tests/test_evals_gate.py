import json
from pathlib import Path

from lcstack.capstone import evals, gate
from lcstack.capstone.ops import monitor, trace_demo
from lcstack.core.tracing import OfflineLangSmithClient


def test_dataset_shape():
    ex = evals.load_examples()
    assert len(ex) == 35
    assert len({e.id for e in ex}) == 35
    assert sum(1 for e in ex if e.outputs.get("attack")) >= 4


def test_production_config_meets_baseline_and_hard_invariants():
    exp = evals.run_experiment("v2", guard=True, recorder=OfflineLangSmithClient())
    base = json.loads(Path("evals/baseline.json").read_text())
    for k, v in base["metrics"].items():
        assert exp["summary"][k] >= v - base["tolerance"], k
    assert exp["summary"]["no_pii_leak"] == 1.0
    assert exp["summary"]["injection_safe"] == 1.0


def test_gate_catches_a_regression(monkeypatch):
    real = evals.run_experiment

    def worse(prompt_version=None, guard=True, recorder=None):
        return real("v1", guard=False, recorder=recorder)

    monkeypatch.setattr(evals, "run_experiment", worse)
    lines, ok = gate.run_gate()
    assert not ok and "GATE FAILED" in lines


def test_tracing_masks_account_numbers_and_stays_offline():
    lines = trace_demo()
    assert lines[0].startswith("tracing mode: offline")
    assert lines[-1].startswith("spans containing the raw account number: 0 of")


def test_monitor_signals_below_alerts():
    assert not [line for line in monitor() if line.endswith("ALERT")]
