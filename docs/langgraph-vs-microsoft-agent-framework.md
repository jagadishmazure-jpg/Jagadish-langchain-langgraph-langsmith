# LangGraph versus Microsoft Agent Framework

I build with both: LangGraph/LangChain in this repository and in
[Jagadish-agentic-ai](https://github.com/jagadishmazure-jpg/Jagadish-agentic-ai), and Microsoft Agent
Framework (MAF) in [Jagadish-azure-agent-platform](https://github.com/jagadishmazure-jpg/Jagadish-azure-agent-platform),
[Jagadish-azure-agent-labs](https://github.com/jagadishmazure-jpg/Jagadish-azure-agent-labs) and
[Jagadish-azure-ai-integration-platform](https://github.com/jagadishmazure-jpg/Jagadish-azure-ai-integration-platform).
This page is how I choose for a client. It compares concepts, not benchmarks; no performance numbers are claimed.

## Concept map

| Concept | LangGraph / LangChain 1.x | Microsoft Agent Framework 1.x |
|---|---|---|
| Single agent | `create_agent` (scenario 8) | an agent built from a chat client |
| Cross-cutting hooks | agent middleware (scenario 9) | agent and function middleware |
| Graph | `StateGraph`: nodes, edges, shared state with reducers | `WorkflowBuilder`: executors, edges and conditions, typed messages |
| Code-first workflow | Functional API, `@entrypoint` / `@task` (scenario 20) | functional `@workflow` / `@step` (Python, experimental at the time of writing) |
| Execution model | super-steps, checkpoint per step | super-steps, checkpoint at superstep boundaries |
| Durable state | checkpointers: memory, SQLite, Postgres (scenario 15) | checkpoint storage: memory, file, Cosmos DB |
| Human in the loop | `interrupt()` + `Command(resume=...)` (scenario 16) | `request_info` events and response handlers |
| Multi-agent patterns | supervisor, handoff with `Command.PARENT`, subgraphs (scenario 19) | sequential, concurrent, handoff, group chat, Magentic orchestrations |
| Tools from other teams | MCP via `langchain-mcp-adapters` (scenario 7) | MCP and A2A built in |
| Languages | Python, JavaScript/TypeScript | Python and .NET |
| Observability | LangSmith (native), OpenTelemetry export | OpenTelemetry; Azure AI Foundry / Application Insights |
| Evaluation | LangSmith datasets, `evaluate`, online evaluators | Azure AI Foundry evaluations and the Azure AI evaluation SDK |
| Serving | Agent Server (`langgraph.json`), managed or self-hosted | your own host (Container Apps, Functions, App Service) or Foundry Agent Service |

## How I choose

| Client situation | Lean towards |
|---|---|
| .NET shop, Microsoft 365 / Copilot surfaces, Foundry already approved | MAF |
| Python-first team, wants the largest integration ecosystem and LangSmith tracing/evals | LangGraph |
| Needs very fine control of state merging and time travel | LangGraph (reducers, `update_state`, forks) |
| Needs agent-to-agent interop with other vendors' agents | either; MAF has A2A built in, LangGraph via adapters or the Agent Server |
| Strict "everything inside our Azure tenant" | either: MAF on Azure, or self-hosted Agent Server (this repo's templates) |
| Existing AutoGen or Semantic Kernel code | MAF (its successor) |
| Existing LangChain code | LangGraph / `create_agent` (scenario 24 shows the migration) |

The patterns transfer: tool rules in code, identity from context, HITL on risky actions, allowlists,
datasets before prompts, gates with hard safety floors. The guardrail design in this repository's capstone
is the same as the one I use on MAF; only the hook names change.

## Things that differ in practice

- **State.** LangGraph shares one state object with per-key reducers; MAF passes typed messages between
  executors and each executor owns its state. LangGraph makes concurrent writes explicit; MAF makes data
  flow explicit.
- **Resume.** LangGraph re-runs the interrupted node from its first line (scenario 23's double side effect);
  in MAF the response is routed to a handler. Both need idempotent side effects.
- **Tracing.** LangSmith gives run trees and evals out of the box; MAF emits OpenTelemetry that lands in
  Application Insights / Foundry. For a mixed estate, export both to OpenTelemetry.

Check the current documentation of both before a client decision; both frameworks move quickly.
