# Adopt this in a client project

A short path from this repository to a client's first production agent.

1. **Pick the layer** with scenario 2's chooser. Most first agents are `create_agent` plus middleware.
2. **Copy the core**: `core/models.py` (one switch for scripted versus real models), `core/tracing.py`
   (both-switch rule, client-side masking), `core/persist.py` (checkpointer with a type allowlist).
3. **Write the dataset before the prompt.** Start with 30-50 labelled cases from real tickets, including
   attacks and out-of-scope requests. Use `capstone/evals.py` as the evaluator template.
4. **Put rules in tools**, identity in `context`, money movement behind HITL, and an allowlist per agent.
5. **Gate releases** with `lcstack gate`-style thresholds; give safety metrics a hard floor of 1.0.
6. **Turn on LangSmith** in staging with masking on the client; promote failing traces into the dataset.
7. **Serve** with `langgraph.json` and the Agent Server; choose managed or self-hosted with the table in
   [deployment.md](deployment.md).
8. **Infrastructure**: start from `infra/terraform` with `private_networking = true` for regulated clients.

Questions to ask the client in week one: which actions move money or change records (those get HITL),
where identity comes from, what data may leave the tenant (traces), and who owns each tool.
