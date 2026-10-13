# Glossary

| Term | Meaning here |
|---|---|
| Agent Server | LangChain's HTTP server for graphs: assistants, threads, runs, streaming, crons (`langgraph dev` locally) |
| Checkpointer | Saves graph state after each super-step under a `thread_id` (InMemory, SQLite, Postgres) |
| Command | A node return value that updates state and chooses the next node; `Command(resume=...)` resumes an interrupt |
| `context` / `context_schema` | Per-run, trusted data (customer id, store id) passed to tools and nodes; not stored in state |
| create_agent | The LangChain 1.x agent loop, a compiled LangGraph graph with middleware hooks |
| Dataset / Example | Labelled inputs and reference outputs used by `langsmith.evaluate` |
| Evaluator | A function scoring a run against its reference (heuristic or LLM-as-judge) |
| HITL | Human in the loop: `interrupt()` pauses, a person decides, the run resumes |
| LCEL | LangChain Expression Language: composing runnables with `|` |
| MCP | Model Context Protocol: tools served by a separate process, loaded with `langchain-mcp-adapters` |
| Middleware | Hooks around the agent loop (`before_model`, `wrap_tool_call`, ...) for cross-cutting controls |
| Reducer | How a state key merges concurrent or repeated updates (`add_messages`, `operator.add`, custom) |
| Run tree | The nested spans of one invocation as stored by LangSmith |
| Scripted model | This repo's deterministic chat model, used so everything runs without keys |
| Send | Fan-out of one node per item at runtime (map-reduce) |
| Store | Long-term memory across threads, organised by namespace |
| Super-step | One round in which all scheduled nodes run, then state merges and a checkpoint is written |
| Thread | One conversation or case; the key of its checkpoints |
