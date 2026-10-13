"""PostgresSaver round trip; runs in CI against the postgres service container (DATABASE_URL)."""

import os

import pytest

from lcstack.scenarios.s15_persistence import postgres_demo, sqlite_restart_demo

pytestmark = pytest.mark.postgres


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs DATABASE_URL (CI postgres service)")
def test_postgres_saver_survives_new_connection():
    lines = postgres_demo(os.environ["DATABASE_URL"])
    assert lines and not any("error" in line.lower() for line in lines)


def test_sqlite_saver_survives_restart(tmp_path):
    lines = sqlite_restart_demo(tmp_path / "cases.db")
    assert lines
