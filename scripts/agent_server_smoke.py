"""Start the local Agent Server (`langgraph dev`, in-memory runtime, no API keys) and drive both
registered graphs through the SDK: create a thread, run to completion, read the thread state.

    python scripts/agent_server_smoke.py

Used by CI. Nothing is deployed; the server listens on 127.0.0.1 only and is stopped afterwards.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

PORT = int(os.getenv("SMOKE_PORT", "2024"))
URL = f"http://127.0.0.1:{PORT}"


def wait_ready(proc: subprocess.Popen, timeout: float = 90) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            raise SystemExit(f"langgraph dev exited with {proc.returncode}")
        try:
            with urllib.request.urlopen(f"{URL}/ok", timeout=2) as r:
                if r.status == 200:
                    return
        except OSError:
            time.sleep(1)
    raise SystemExit("Agent Server did not become ready")


def main() -> int:
    from langgraph_sdk import get_sync_client

    env = {**os.environ, "LANGSMITH_TRACING": "false", "LANGGRAPH_NO_BROWSER": "1"}
    env.pop("LANGSMITH_API_KEY", None)
    exe = shutil.which("langgraph") or "langgraph"
    proc = subprocess.Popen([exe, "dev", "--no-browser", "--no-reload", "--host", "127.0.0.1", "--port", str(PORT)], env=env)
    ok = True
    try:
        wait_ready(proc)
        client = get_sync_client(url=URL)
        assistants = sorted(a["graph_id"] for a in client.assistants.search())
        print(f"assistants registered: {assistants}")
        cases = [
            ("support_desk", {"messages": [{"role": "user", "content": "What are the wire transfer cutoff times?"}]}, {"customer_id": "C-100"}),
            (
                "scheduling_assistant",
                {"messages": [{"role": "user", "content": "I need a dermatology appointment, mornings please"}]},
                {"patient_id": "P-301"},
            ),
        ]
        for graph_id, payload, context in cases:
            thread = client.threads.create()
            kwargs = {"input": payload}
            if context:
                kwargs["context"] = context
            out = client.runs.wait(thread["thread_id"], graph_id, **kwargs)
            last = out["messages"][-1]["content"] if isinstance(out, dict) and out.get("messages") else out
            state = client.threads.get_state(thread["thread_id"])
            print(f"{graph_id}: {str(last)[:160]!r}; checkpoint saved by the server: {bool(state['checkpoint'])}")
            ok &= bool(last) and bool(state["checkpoint"])
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("agent server smoke: PASS" if ok else "agent server smoke: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
