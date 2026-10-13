"""Every test runs offline: LangSmith tracing off unless both switches are set, and outbound sockets blocked."""

from __future__ import annotations

import os
import socket

import pytest

for k in ("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"):
    os.environ.pop(k, None)
os.environ["LANGSMITH_TRACING"] = "false"
os.environ.setdefault("LCSTACK_MODEL", "scripted")

_real_connect = socket.socket.connect
ALLOWED = {"127.0.0.1", "::1", "localhost"}


def _guarded_connect(self, address):
    host = address[0] if isinstance(address, tuple) else None
    if host is not None and host not in ALLOWED and not os.getenv("DATABASE_URL"):
        raise RuntimeError(f"test tried to reach the network: {address}")
    return _real_connect(self, address)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    yield
