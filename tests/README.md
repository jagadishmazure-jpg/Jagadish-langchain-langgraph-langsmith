# tests

All offline: `conftest.py` removes keys, disables LangSmith tracing and blocks outbound sockets.

| File | What it covers |
|---|---|
| `test_scenarios.py` | all 25 scenarios run, are deterministic and have a README |
| `test_s23_gotchas.py` | each gotcha's broken symptom and its fix |
| `test_s24_migration.py` | legacy AgentExecutor versus create_agent parity; import lint |
| `test_capstone.py` | routing, injection (direct, tool output, RAG), HITL reject, output validation |
| `test_evals_gate.py` | dataset shape, baseline, gate catches a regression, trace masking, monitoring |
| `test_persistence_postgres.py` | PostgresSaver (CI service container) and SQLite restart |
| `test_iac_workflows.py` | Terraform/Bicep invariants and workflow hardening |
| `test_repo_hygiene.py` | links, dates, secrets, fictional names, attribution, no reference PDF |
