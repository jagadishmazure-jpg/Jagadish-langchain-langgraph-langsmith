"""Entry point named by ``foundry/azure.yaml``.

The default process prints the offline transcript. ``--live`` refuses to start the Azure host, so
this module cannot be pointed at a real project by accident.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m lcstack.foundry.serve")
    parser.add_argument("--protocol", choices=["responses", "invocations"], default="responses")
    parser.add_argument("--live", action="store_true", help="guard: do not start the Azure host")
    args = parser.parse_args(argv)
    if args.live:
        try:
            import langchain_azure_ai.agents.hosting  # noqa: F401
        except ImportError:
            print("langchain-azure-ai[hosting] is not installed. This repository runs the offline stand-in.")
        else:
            print("langchain-azure-ai is importable, and this repository still refuses to start it.")
        print("Deploy from a Foundry project with azd. This package does not call Azure.")
        return 2
    from lcstack.foundry.desk import demo, invocations_probe

    lines = demo() if args.protocol == "responses" else invocations_probe()
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
