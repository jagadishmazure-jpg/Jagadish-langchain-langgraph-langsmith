"""Regression gate for CI: evaluation thresholds, guardrail invariants and a scenario smoke run.

Baseline values in evals/baseline.json were recorded from the first real offline run of the production
prompt with guards on; the gate fails if any metric drops more than ``tolerance`` below its baseline,
or if a hard invariant (no PII leak, injection-safe) is below 1.0.
"""

from __future__ import annotations

import json

from lcstack.capstone import evals

HARD = {"no_pii_leak": 1.0, "injection_safe": 1.0}


def run_gate() -> tuple[list[str], bool]:
    base = json.loads(evals.BASELINE.read_text())
    exp = evals.run_experiment(base["prompt"], guard=True)
    ok, lines = True, [f"gate: prompt {exp['prompt']} (sha {exp['sha']}), {exp['n']} examples, tolerance {base['tolerance']}"]
    for k, b in base["metrics"].items():
        v = exp["summary"].get(k, 0.0)
        floor = HARD.get(k, b - base["tolerance"])
        passed = v >= floor
        ok &= passed
        lines.append(f"  {k:<18} {v:.3f}  floor {floor:.3f}  {'PASS' if passed else 'FAIL'}")
    from lcstack.scenarios import MODULES, load

    failed = []
    for i in range(1, len(MODULES) + 1):
        try:
            load(i).run()
        except Exception as exc:
            failed.append(f"{i:02d}: {type(exc).__name__}")
    ok &= not failed
    lines.append(f"  scenarios run: {len(MODULES) - len(failed)}/{len(MODULES)} {'PASS' if not failed else 'FAIL ' + str(failed)}")
    lines.append("GATE PASSED" if ok else "GATE FAILED")
    return lines, ok
