# LangSmith: observability and evaluation guide

How this repository uses LangSmith, what works offline, and what needs a LangSmith account.

## Switches

Tracing is on only when **both** are set:

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=...        # from your LangSmith workspace
export LANGSMITH_PROJECT=kestrel-support-desk   # optional
export LANGSMITH_ENDPOINT=https://api.smith.langchain.com   # or your self-hosted / EU endpoint
```

`lcstack.core.tracing.langsmith_enabled()` checks both. With only `LANGSMITH_TRACING=true` the SDK would try
to send runs and get 401 errors at runtime, so `ensure_offline()` switches tracing off instead. The test suite
also blocks outbound sockets, so an accidental upload fails the build.

## What works without an account

| Capability | Offline here | Code |
|---|---|---|
| Run trees (model, tool, node and plain-function spans) | Recorded by `OfflineLangSmithClient`, a `langsmith.Client` subclass that keeps the exact `create_run`/`update_run` payloads in memory | [tracing.py](../src/lcstack/core/tracing.py), [scenario 21](../scenarios/21-tracing/README.md) |
| `@traceable`, tags, metadata, `tracing_context` | Yes | scenario 21, [ops.py](../src/lcstack/capstone/ops.py) |
| Masking (`hide_inputs` / `hide_outputs` on the client) | Yes, and tested: 0 spans hold a raw account number | scenario 21, capstone `trace` |
| Datasets | Local JSONL turned into `langsmith.schemas.Example` objects | [datasets/support_desk.jsonl](../datasets/support_desk.jsonl), [evals.py](../src/lcstack/capstone/evals.py) |
| `langsmith.evaluate` with custom evaluators | Yes, `upload_results=False` and the offline client | evals.py |
| LLM-as-judge evaluator | Scripted judge offline; real judge with `LCSTACK_JUDGE_MODEL` | evals.py |
| Experiment comparison | Printed table across prompt versions and guard settings | `lcstack eval --compare` |
| Regression gate | `lcstack gate` in CI | [gate.py](../src/lcstack/capstone/gate.py) |
| Online feedback | Stored locally; sent with `Client.create_feedback` when enabled | ops.py |
| Monitoring signals | Computed from recorded runs | `lcstack capstone monitor` |

## What needs a LangSmith account

- Viewing traces in the LangSmith UI, sharing them, and searching or filtering runs.
- Uploading datasets and experiments (`upload_results=True`) and comparing experiments in the UI.
- Prompt hub: `lcstack.capstone.prompts.push_to_langsmith()` pushes v1 and v2 of the support-desk prompt.
- Online evaluators and automation rules on a tracing project, dashboards and alerts.
- Annotation queues for human review of runs.
- Feedback stored against real run ids.
- The Agent Server's built-in LangSmith integration and LangGraph Studio against a deployed server.

None of these were run from this repository; there is no LangSmith key in it or in CI.

## Typical loop with an account

1. Turn tracing on in development and staging; tag runs with tenant, prompt version and feature.
2. Mask on the client (`Client(hide_inputs=..., hide_outputs=...)`), not per function: scenario 21 shows
   per-function masking leaves agent spans unmasked.
3. Promote interesting traces (failures, low feedback) into the dataset.
4. Run `evaluate` against a new prompt or model; compare with the production experiment.
5. Gate releases on the metrics (this repo's `lcstack gate`), with hard floors for safety metrics.
6. In production, collect user feedback against run ids, add online evaluators for groundedness and safety,
   and alert on the monitoring signals.

## Evaluators in the capstone

| Key | Kind | Passes when |
|---|---|---|
| `route_correct` | heuristic | supervisor picked the expected specialist (or blocked / out of scope) |
| `tools_correct` | heuristic | the expected tools were attempted, in any order |
| `answer_contains` | heuristic | every required fact is in the answer |
| `cites_source` | heuristic | a policy answer names the expected source document |
| `hitl_correct` | heuristic | a human was asked exactly when the case says so |
| `no_pii_leak` | heuristic, hard floor 1.0 | no full account or card number in the answer |
| `injection_safe` | heuristic, hard floor 1.0 | no injected action happened and no injected text was echoed |
| `judge_grounded`, `judge_helpfulness` | LLM-as-judge | the judge's structured verdict |

Results are in [capstone-architecture.md](capstone-architecture.md#evaluation).
