"""Entry point for the Agent Server (langgraph.json -> support_desk).

No checkpointer is passed: ``langgraph dev`` (in memory) and a deployed server (Postgres) provide
their own, plus threads, runs, streaming and cron over HTTP.
"""

from lcstack.capstone.graph import build

graph = build()
