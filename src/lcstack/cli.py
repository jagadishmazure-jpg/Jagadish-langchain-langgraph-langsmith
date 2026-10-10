"""Command line: ``lcstack list``, ``lcstack run NN``, ``lcstack capstone ...``, ``lcstack eval``, ``lcstack gate``."""

from __future__ import annotations

import argparse
import sys

from lcstack.core.tracing import ensure_offline


def _print(lines: list[str]) -> None:
    for line in lines:
        print(line.rstrip())


def main(argv: list[str] | None = None) -> int:
    ensure_offline()
    ap = argparse.ArgumentParser(prog="lcstack", description="LangChain, LangGraph and LangSmith scenarios, offline by default.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the 25 scenarios")
    r = sub.add_parser("run", help="run one scenario")
    r.add_argument("number", type=int)
    c = sub.add_parser("capstone", help="the end-to-end support system")
    c.add_argument("action", choices=["demo", "trace", "stream", "hitl", "monitor", "feedback", "prompts", "architecture"])
    e = sub.add_parser("eval", help="run the capstone evaluation on the dataset")
    e.add_argument("--prompt", default=None, help="prompt version to evaluate (default: the production one)")
    e.add_argument("--compare", action="store_true", help="compare every prompt version")
    sub.add_parser("gate", help="regression gate: evaluation thresholds, guardrails, scenarios")
    li = sub.add_parser("lint-imports", help="flag pre-1.0 LangChain imports in Python files")
    li.add_argument("paths", nargs="+")
    a = ap.parse_args(argv)

    if a.cmd == "list":
        from lcstack.scenarios import all_meta

        for m in all_meta():
            print(f"{m.number:02d}  {m.section:<28} {m.client}")
        return 0
    if a.cmd == "run":
        from lcstack.scenarios import load

        _print(load(a.number).run())
        return 0
    if a.cmd == "lint-imports":
        from lcstack.scenarios.s25_import_map import lint_paths

        lines, bad = lint_paths(a.paths)
        _print(lines)
        return 1 if bad else 0
    if a.cmd == "capstone":
        from lcstack.capstone import cli as ccli

        _print(ccli.action(a.action))
        return 0
    if a.cmd == "eval":
        from lcstack.capstone import evals

        _print(evals.report(prompt=a.prompt, compare=a.compare))
        return 0
    if a.cmd == "gate":
        from lcstack.capstone import gate

        lines, ok = gate.run_gate()
        _print(lines)
        return 0 if ok else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
