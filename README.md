# LangChain, LangGraph and LangSmith, end to end

25 runnable client scenarios, one per section of a LangChain/LangGraph cheat sheet, and a capstone
multi-agent support desk with RAG, tools, MCP, guardrails, human approval, persistence, streaming,
LangSmith tracing, datasets, evaluations, prompt versions, feedback and monitoring.

Everything runs **offline with no API keys**, in CI and on a laptop. Companies are fictional:
Wrenfield Grocers (retail), Kestrel Ridge Bank (banking), Halsey Vale Health (healthcare), Ferrowind
Insurance (insurance) and Quillmere Home Loans (mortgage). Nothing has been deployed.

**For a quick read:** the [capstone architecture](docs/capstone-architecture.md) (real eval numbers), the
[security threat model](docs/security.md), [LangGraph vs Microsoft Agent Framework](docs/langgraph-vs-microsoft-agent-framework.md)
and [limitations](docs/limitations.md).

## Quick start

```bash
uv venv -p 3.13 && source .venv/bin/activate
uv pip sync requirements.lock && uv pip install --no-deps -e .
lcstack list                 # the 25 scenarios
lcstack run 16               # any scenario: real output from the scripted model
lcstack capstone demo        # support desk conversations (also: trace, stream, hitl, monitor, feedback, prompts)
lcstack eval --compare       # offline LangSmith evaluation: prompt v1/v2, guards on/off
lcstack gate                 # the CI regression gate
pytest -q
```

Real models are optional: `LCSTACK_MODEL=azure` uses Azure OpenAI with an Entra ID token (no key), or any
`provider:model` string. LangSmith tracing turns on only when both `LANGSMITH_TRACING=true` and
`LANGSMITH_API_KEY` are set; see the [LangSmith guide](docs/langsmith-guide.md) for what needs an account.

## The 25 scenarios

<!-- BEGIN scenario-table -->
| # | Section | Concept | Client use case (fictional) | Folder | Command | Tests |
|---|---|---|---|---|---|---|
| 01 | The Ecosystem | Package map: langchain, langchain-core, langgraph, langsmith, deepagents, integrations, langchain-classic | Wrenfield Grocers: platform dependency audit | [scenarios/01-ecosystem](scenarios/01-ecosystem/README.md) | `lcstack run 01` | [test_scenarios.py](tests/test_scenarios.py) |
| 02 | Which Layer to Use | Model+LCEL vs create_agent vs deep agents vs Graph API vs Functional API, plus a layer chooser | Kestrel Ridge Bank: card-dispute intake built five ways | [scenarios/02-which-layer](scenarios/02-which-layer/README.md) | `lcstack run 02` | [test_scenarios.py](tests/test_scenarios.py) |
| 03 | Install and Chat Models | init_chat_model provider strings; invoke, stream, batch, ainvoke/abatch; usage metadata | Halsey Vale Health: patient-portal FAQ answers | [scenarios/03-chat-models](scenarios/03-chat-models/README.md) | `lcstack run 03` | [test_scenarios.py](tests/test_scenarios.py) |
| 04 | Messages | System/Human/AI/Tool messages, dict form, multimodal blocks, tool_call_id pairing, trimming, serialisation | Quillmere Home Loans: borrower chat transcripts for audit | [scenarios/04-messages](scenarios/04-messages/README.md) | `lcstack run 04` | [test_scenarios.py](tests/test_scenarios.py) |
| 05 | Prompts and LCEL | ChatPromptTemplate, prompt | model | parser, with_retry, with_fallbacks, RunnableParallel, bind_tools | Ferrowind Insurance: claim-note summaries per audience | [scenarios/05-prompts-lcel](scenarios/05-prompts-lcel/README.md) | `lcstack run 05` | [test_scenarios.py](tests/test_scenarios.py) |
| 06 | Structured Output | with_structured_output(Pydantic), include_raw, create_agent(response_format=ToolStrategy) with error retry | Ferrowind Insurance: FNOL claim triage into a typed record | [scenarios/06-structured-output](scenarios/06-structured-output/README.md) | `lcstack run 06` | [test_scenarios.py](tests/test_scenarios.py) |
| 07 | Tools | @tool, docstring and type hints as schema, errors as text vs raising, ToolNode error handling, MCP via langchain-mcp-adapters | Wrenfield Grocers: order-refund agent with an MCP inventory server | [scenarios/07-tools](scenarios/07-tools/README.md) | `lcstack run 07` | [test_scenarios.py](tests/test_scenarios.py) |
| 08 | create_agent | create_agent with tools, system_prompt, checkpointer, context_schema (ToolRuntime) and response_format | Wrenfield Grocers: billing-ticket agent for store managers | [scenarios/08-create-agent](scenarios/08-create-agent/README.md) | `lcstack run 08` | [test_scenarios.py](tests/test_scenarios.py) |
| 09 | Middleware | before_model with jump_to, HumanInTheLoop, PII, Model/ToolRetry, ToolCallLimit, wrap_tool_call, dynamic_prompt, Summarization | Kestrel Ridge Bank: card-dispute agent under compliance controls | [scenarios/09-middleware](scenarios/09-middleware/README.md) | `lcstack run 09` | [test_scenarios.py](tests/test_scenarios.py) |
| 10 | Retrieval Building Blocks | Loader, RecursiveCharacterTextSplitter, embeddings, InMemoryVectorStore, retriever, retriever as a @tool, recall@k and MRR | Quillmere Home Loans: underwriting-guideline assistant | [scenarios/10-retrieval](scenarios/10-retrieval/README.md) | `lcstack run 10` | [test_scenarios.py](tests/test_scenarios.py) |
| 11 | LangGraph Mental Model | Shared state, nodes as functions returning partial updates, fixed edges, fan-out/fan-in, super-steps, a checkpoint per step | Halsey Vale Health: emergency-department intake | [scenarios/11-mental-model](scenarios/11-mental-model/README.md) | `lcstack run 11` | [test_scenarios.py](tests/test_scenarios.py) |
| 12 | State and Reducers | add_messages (merge by id, RemoveMessage), operator.add, plain overwrite, a custom reducer, Overwrite to bypass a reducer | Wrenfield Grocers: basket assistant state | [scenarios/12-state-reducers](scenarios/12-state-reducers/README.md) | `lcstack run 12` | [test_scenarios.py](tests/test_scenarios.py) |
| 13 | A ReAct Graph by Hand | StateGraph(MessagesState) + bind_tools + ToolNode + tools_condition + checkpointer, compared with create_agent | Ferrowind Insurance: policy-servicing assistant | [scenarios/13-react-by-hand](scenarios/13-react-by-hand/README.md) | `lcstack run 13` | [test_scenarios.py](tests/test_scenarios.py) |
| 14 | Control Flow | add_conditional_edges with a router, Command(goto, update) with typed destinations, Send map-reduce, one routing method per node | Kestrel Ridge Bank: payment-exception routing and statement packs | [scenarios/14-control-flow](scenarios/14-control-flow/README.md) | `lcstack run 14` | [test_scenarios.py](tests/test_scenarios.py) |
| 15 | Persistence | thread_id, InMemorySaver / SqliteSaver / PostgresSaver, get_state, get_state_history, update_state, replay and fork from a checkpoint | Kestrel Ridge Bank: multi-day dispute case workflow | [scenarios/15-persistence](scenarios/15-persistence/README.md) | `lcstack run 15` | [test_persistence_postgres.py](tests/test_persistence_postgres.py), [test_scenarios.py](tests/test_scenarios.py) |
| 16 | Human in the Loop | interrupt() payloads, __interrupt__, Command(resume=...), approve/edit/reject, idempotent side effects, a checkpointer is required | Quillmere Home Loans: underwriter approval of document conditions | [scenarios/16-human-in-the-loop](scenarios/16-human-in-the-loop/README.md) | `lcstack run 16` | [test_scenarios.py](tests/test_scenarios.py) |
| 17 | Long-Term Memory | InMemoryStore with an embedding index, namespaces per user, runtime.store in nodes and tools, context_schema, cross-thread recall | Halsey Vale Health: appointment-scheduling assistant that remembers preferences | [scenarios/17-long-term-memory](scenarios/17-long-term-memory/README.md) | `lcstack run 17` | [test_scenarios.py](tests/test_scenarios.py) |
| 18 | Streaming | stream_mode values / updates / messages / custom / debug, several modes at once, get_stream_writer from a tool, astream | Wrenfield Grocers: order-tracking assistant in the mobile app | [scenarios/18-streaming](scenarios/18-streaming/README.md) | `lcstack run 18` | [test_scenarios.py](tests/test_scenarios.py) |
| 19 | Subgraphs and Multi-Agent | Compiled agents as nodes, a structured-output supervisor router, handoff with Command.PARENT, subgraph private state | Ferrowind Insurance: supervisor with claims, policy and billing specialists | [scenarios/19-multi-agent](scenarios/19-multi-agent/README.md) | `lcstack run 19` | [test_scenarios.py](tests/test_scenarios.py) |
| 20 | Functional API | @entrypoint with a checkpointer, @task futures in parallel, interrupt inside a workflow, tasks not re-run on resume, entrypoint.final | Quillmere Home Loans: nightly rate-lock extension digest | [scenarios/20-functional-api](scenarios/20-functional-api/README.md) | `lcstack run 20` | [test_scenarios.py](tests/test_scenarios.py) |
| 21 | Tracing with LangSmith | LANGSMITH_TRACING / API_KEY / PROJECT, run tree of model/tool/node spans, @traceable for plain code, tags and metadata, input masking, datasets from traces | Kestrel Ridge Bank: fraud-alert explainer with auditable traces | [scenarios/21-tracing](scenarios/21-tracing/README.md) | `lcstack run 21` | [test_scenarios.py](tests/test_scenarios.py) |
| 22 | Deploying | langgraph.json, a server-ready graph (no checkpointer: the server provides one), langgraph dockerfile/build, SDK threads/runs/crons, managed vs self-host | Halsey Vale Health: scheduling assistant behind the Agent Server API | [scenarios/22-deploying](scenarios/22-deploying/README.md) | `lcstack run 22` | [test_scenarios.py](tests/test_scenarios.py) |
| 23 | Gotchas | Missing compile, new thread_id per call, recursion limit placement, reducer growth vs Overwrite, static edge + Command double-run, re-run after interrupt, checkpoint type allowlist | Halsey Vale Health: pharmacy refill workflow, broken then fixed | [scenarios/23-gotchas](scenarios/23-gotchas/README.md) | `lcstack run 23` | [test_s23_gotchas.py](tests/test_s23_gotchas.py), [test_scenarios.py](tests/test_scenarios.py) |
| 24 | Migrating Old Code | AgentExecutor -> create_agent, LLMChain -> LCEL, ConversationBufferMemory -> checkpointer + thread_id, legacy imports -> langchain-classic | Ferrowind Insurance: FNOL bot migrated from AgentExecutor | [scenarios/24-migration](scenarios/24-migration/README.md) | `lcstack run 24` | [test_s24_migration.py](tests/test_s24_migration.py), [test_scenarios.py](tests/test_scenarios.py) |
| 25 | Import Map | Where each building block lives in 1.x (verified by import), and an AST linter that flags pre-1.0 imports | Quillmere Home Loans: import audit across internal agent repos | [scenarios/25-import-map](scenarios/25-import-map/README.md) | `lcstack run 25` | [test_s24_migration.py](tests/test_s24_migration.py), [test_scenarios.py](tests/test_scenarios.py) |
<!-- END scenario-table -->

## Capstone: Kestrel Ridge Bank support desk

`guard_input -> supervisor -> accounts / cards / knowledge / out-of-scope -> validate_output`, with
tool-output screening, per-agent allowlists, HITL on refunds and card orders, PII masking, an MCP server for
branch and FX data, and agentic RAG over eight policy documents (one of them poisoned on purpose).

Regression gate on the production configuration (prompt v2, guards on), 35 labelled cases:

<!-- BEGIN gate -->
```text
gate: prompt v2 (sha 63cf6b5968e5), 35 examples, tolerance 0.02
  route_correct      0.886  floor 0.866  PASS
  tools_correct      0.886  floor 0.866  PASS
  answer_contains    0.857  floor 0.837  PASS
  cites_source       0.818  floor 0.798  PASS
  hitl_correct       0.971  floor 0.951  PASS
  no_pii_leak        1.000  floor 1.000  PASS
  injection_safe     1.000  floor 1.000  PASS
  judge_grounded     1.000  floor 0.980  PASS
  judge_helpfulness  0.893  floor 0.873  PASS
  scenarios run: 25/25 PASS
GATE PASSED
```
<!-- END gate -->

The full comparison (v1 versus v2, guards on and off), the honest reading of the misses, monitoring and
feedback are in [docs/capstone-architecture.md](docs/capstone-architecture.md). Offline numbers measure the
pipeline and guardrails with a scripted model and a scripted judge, not model quality.

## Documentation

| Doc | What it is |
|---|---|
| [docs/capstone-architecture.md](docs/capstone-architecture.md) | capstone design and generated outputs |
| [docs/langsmith-guide.md](docs/langsmith-guide.md) | tracing, datasets, evaluators, gate; offline versus account |
| [docs/deployment.md](docs/deployment.md) | langgraph.json, Agent Server, managed versus self-hosted, Azure templates |
| [docs/security.md](docs/security.md) | STRIDE, OWASP LLM Top 10 (2025), MITRE ATLAS, controls with tests |
| [docs/langgraph-vs-microsoft-agent-framework.md](docs/langgraph-vs-microsoft-agent-framework.md) | how I choose |
| [docs/adopt-this.md](docs/adopt-this.md) | path to a client's first production agent |
| [docs/limitations.md](docs/limitations.md) | built versus planned |
| [docs/glossary.md](docs/glossary.md), [docs/adr](docs/adr/) | terms and six decision records |
| [infra](infra/README.md) | Terraform and Bicep for Azure Container Apps, Postgres, Redis, Key Vault (never applied) |

## Status

| Built and tested | Documented, needs an account or a cloud |
|---|---|
| 25 scenarios, capstone, offline evals and gate | LangSmith UI, hub, uploaded experiments, online evaluators |
| PostgresSaver against a CI service container | real-model evaluation runs |
| Local Agent Server driven by the SDK in CI | managed or self-hosted deployment |
| Terraform (`terraform test`, tflint, checkov) and Bicep build | applying the templates (deploy workflow gated off) |

<!-- BEGIN test-count -->
**175 tests** (`pytest --collect-only -q`), plus 3 `terraform test` runs.
<!-- END test-count -->

## Related repositories

[Jagadish-agentic-ai](https://github.com/jagadishmazure-jpg/Jagadish-agentic-ai) (21 LangGraph/LangChain projects),
[Jagadish-azure-agent-platform](https://github.com/jagadishmazure-jpg/Jagadish-azure-agent-platform) (Microsoft Agent Framework on Azure),
[Jagadish-azure-ai-soc](https://github.com/jagadishmazure-jpg/Jagadish-azure-ai-soc),
[Jagadish-agent-auth-security](https://github.com/jagadishmazure-jpg/Jagadish-agent-auth-security).

## Credits and licence

Section titles follow the *LangChain & LangGraph Cheat Sheet* by AI Engineering Insider. The cheat sheet
is not included and its text is not reproduced; all code and prose here are original
(`scripts/overlap_check.py` reports 0 overlapping 8-word runs against it). MIT licence, see [LICENSE](LICENSE).
Security reports: [SECURITY.md](SECURITY.md).
