# Limitations

Honest list of what this repository is and is not.

## Built versus planned

| Item | Status |
|---|---|
| 25 scenarios, offline, deterministic, tested | built |
| Capstone graph, guardrails, HITL, MCP, streaming, tracing (offline), evals, gate, feedback, monitoring | built |
| PostgresSaver | built, tested in CI against a `postgres:17` service container (not on the dev box, which has no Docker) |
| Agent Server | built and started locally in CI with `langgraph dev`; never deployed |
| Terraform and Bicep for Azure | built and statically tested; never applied |
| Deploy and teardown workflows | built, gated off (`DEPLOY_ENABLED` not set) |
| Real model runs (Azure OpenAI via Entra ID) | wired (`LCSTACK_MODEL=azure`), not run in CI; no results are claimed |
| LangSmith UI, hub, uploaded experiments, online evaluators | documented, need an account; not run |

## Models and numbers

- The scripted model follows playbooks keyed on the prompt rules and the request; it makes evaluation
  reproducible but it is not a language model. Eval numbers measure the pipeline, guards and prompt wiring,
  not model quality.
- The offline judge is scripted too. Judge scores offline demonstrate the evaluator, not real grading.
- Token counts are simulated by the scripted model. Latency is never reported.
- `HashingEmbeddings` is lexical; retrieval scores in scenario 10 do not represent semantic embeddings.

## Guardrails

- Injection screens are regular expressions; they catch the attack phrasings in the dataset and obvious
  variants, not adaptive attacks.
- The supervisor's router is keyword-based; the dataset keeps its misses visible.

## Infrastructure

- Terraform stores generated connection strings (Postgres password, Redis key) in state; use a state
  storage account with Entra auth, private access and restricted RBAC.
- The Agent Server uses a Postgres password (its `DATABASE_URI` does not refresh Entra tokens); Entra auth is
  enabled on the server for operators.
- Container Apps is a pragmatic choice; LangChain recommends Kubernetes for self-hosted production.
- checkov findings that depend on `private_networking` or on Premium SKUs are skipped inline with a reason.
- Container image scanning (Defender for Containers) is out of scope of the stack.
