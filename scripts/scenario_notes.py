"""Hand-written notes for each scenario README. Output and code excerpts are generated, never pasted."""

N = {
    1: dict(
        excerpts=["audit", "create_agent_is_a_graph"],
        mermaid="flowchart LR\n  core[langchain-core<br/>messages, runnables, tools] --> lc[langchain<br/>create_agent, middleware]\n  core --> lg[langgraph<br/>graphs, checkpoints]\n  lg --> lc\n  lc --> da[deepagents]\n  lc -.legacy.-> cl[langchain-classic]\n  ls[langsmith<br/>traces, evals] -.observes.-> lc & lg",
        how=[
            "Each package entry names the symbols teams depend on; the audit imports them from the installed version and reports what was found.",
            "`create_agent_is_a_graph` shows that the 1.x agent is a compiled LangGraph graph, so everything in sections 11-20 applies to it.",
        ],
        gotchas=[
            "Integration packages (`langchain-openai`, ...) are versioned separately from `langchain`; pin both.",
            "Chains, memory classes and `AgentExecutor` now live in `langchain-classic`, not `langchain`.",
        ],
        interview=[
            "langchain-core is the contract layer; langgraph is the runtime; langchain 1.x is the opinionated agent layer on top.",
            "LangSmith is framework-agnostic: `@traceable` works on plain Python.",
        ],
    ),
    2: dict(
        excerpts=["via_lcel", "via_create_agent", "choose_layer"],
        mermaid="flowchart TD\n  q{Needs tools?} -- no --> lcel[Model + LCEL]\n  q -- yes --> p{Planning, files,<br/>sub-agents?}\n  p -- yes --> deep[Deep agent]\n  p -- no --> c{Custom control flow,<br/>parallel steps?}\n  c -- no --> agent[create_agent]\n  c -- yes --> s{Prefer plain Python?}\n  s -- yes --> fn[Functional API]\n  s -- no --> graph[Graph API]",
        how=[
            "The same dispute message is classified and acknowledged by five implementations; all must agree on the category.",
            "Each implementation reports its machinery (model calls, nodes, checkpoints) so the cost of each layer is visible.",
            "`choose_layer` encodes the decision tree above and is unit-tested against representative requirements.",
        ],
        gotchas=[
            "Starting with the Graph API for a single-prompt task adds state and wiring with no benefit.",
            "Deep agents bring a filesystem and planning tools; use them when the task needs them.",
        ],
        interview=[
            "Pick the highest layer that fits and drop down only for a concrete need.",
            "All five share the same model, message and tool abstractions, so moving between layers is cheap.",
        ],
    ),
    3: dict(
        excerpts=["provider_table", "_async_demo"],
        mermaid="flowchart LR\n  app[Portal FAQ] --> m[chat model]\n  m -->|invoke| one[one answer]\n  m -->|stream| tok[token chunks]\n  m -->|batch| many[nightly refresh]\n  m -->|ainvoke / abatch| api[API gateway]",
        how=[
            "`init_chat_model` turns a `provider:model` string into a chat model; the table shows the strings for the providers a client might use.",
            "One model object serves invoke, stream, batch and the async variants; usage metadata is read from the AI message.",
        ],
        gotchas=[
            "`batch` runs requests concurrently; set `max_concurrency` to respect provider rate limits.",
            "Token counts in this repo come from the scripted model and are not provider numbers.",
        ],
        interview=[
            "Provider-agnostic code means swapping Azure OpenAI for another provider is a config change (`LCSTACK_MODEL`).",
            "Async matters when one process serves many conversations.",
        ],
    ),
    4: dict(
        excerpts=["build_transcript", "unanswered_or_orphaned"],
        mermaid="flowchart LR\n  w[widget dicts] --> n[message classes]\n  n --> c{every ToolMessage<br/>answers a tool call?}\n  c --> t[trim to budget]\n  t --> j[JSON for audit]\n  j --> n",
        how=[
            "Dict-form messages from the web widget are normalised into typed messages, including an image content block.",
            "A check pairs each ToolMessage with its AIMessage tool call by `tool_call_id`.",
            "`trim_messages` keeps the newest history within a budget, starting on a human turn; messages round-trip through JSON.",
        ],
        gotchas=[
            "A ToolMessage without its matching tool call is rejected by most providers.",
            "Trimming can split a tool call from its result; trim on turn boundaries.",
        ],
        interview=[
            "Messages are the common currency between models, tools and graphs.",
            "Store transcripts in the serialised message format so they can be replayed.",
        ],
    ),
    5: dict(
        excerpts=["get_policy"],
        mermaid="flowchart LR\n  note[claim note] --> p[ChatPromptTemplate]\n  p --> m[model<br/>with_retry, with_fallbacks]\n  m --> o[StrOutputParser]\n  note --> par[RunnableParallel]\n  par --> s[summary] & e[entities]",
        how=[
            "One prompt template per audience feeds a model piped into a parser.",
            "`with_retry` absorbs transient failures of the primary endpoint and `with_fallbacks` switches to a backup model.",
            "`RunnableParallel` produces the summary and the entity extraction in one call; `bind_tools` attaches a policy lookup.",
        ],
        gotchas=["`with_fallbacks` only triggers on exceptions, not on a poor answer.", "Retrying non-idempotent calls can duplicate side effects."],
        interview=[
            "LCEL is still the right tool for fixed pipelines with no agent loop.",
            "Every runnable gets invoke, stream, batch and async for free.",
        ],
    ),
    6: dict(
        excerpts=["ClaimTriage", "_sloppy_then_fixed"],
        mermaid="flowchart LR\n  fnol[FNOL text] --> so[with_structured_output]\n  so --> ct[ClaimTriage]\n  fnol --> ag[create_agent<br/>response_format=ToolStrategy]\n  ag -->|invalid| retry[error fed back] --> ag\n  ag --> ct",
        how=[
            "`with_structured_output(ClaimTriage)` returns a validated Pydantic object; `include_raw=True` also keeps the raw message.",
            "In an agent, `ToolStrategy` turns the schema into a tool; an invalid first attempt is fed back as an error and the model corrects it.",
        ],
        gotchas=[
            "Validation errors must reach the model as feedback, not crash the run.",
            "Field descriptions are part of the prompt; vague ones give vague output.",
        ],
        interview=[
            "Typed outputs are what let an LLM step feed a system of record.",
            "Prefer provider-native structured output when available; ToolStrategy works everywhere.",
        ],
    ),
    7: dict(
        excerpts=["refund_order", "tool_node_graph", "mcp_demo"],
        mermaid="flowchart LR\n  m[model] -->|tool call| tn[ToolNode]\n  tn --> r[refund_order<br/>rules in code]\n  tn --> g[payments gateway]\n  tn --> mcp[MCP server<br/>inventory, loyalty]\n  r -->|error as text| m",
        how=[
            "`@tool` builds the schema from type hints and the docstring; refund rules are enforced in the function.",
            "Recoverable errors return text the model can act on; an outage raises, and ToolNode's error handling decides what the model sees.",
            "`langchain-mcp-adapters` loads tools from a stdio MCP server (`s07_mcp_server.py`).",
        ],
        gotchas=[
            "A tool that raises on a user mistake ends the run; return a message instead.",
            "MCP tools are async; call the agent with `ainvoke`.",
        ],
        interview=[
            "Business rules belong in tools, where they are testable, not in the prompt.",
            "MCP lets another team own a tool server without sharing code.",
        ],
    ),
    8: dict(
        excerpts=["StoreCtx", "get_invoice", "build"],
        mermaid="flowchart LR\n  u[store manager] --> a[create_agent]\n  a --> t[get_invoice<br/>reads runtime.context]\n  a --> cp[(checkpointer<br/>thread_id)]\n  a --> out[TicketOutcome]",
        how=[
            "Tools read the store and user from `runtime.context` (the `context_schema`), not from chat text.",
            "A checkpointer plus `thread_id` gives each ticket its own memory; `response_format` returns a typed outcome.",
        ],
        gotchas=[
            "Without a checkpointer the agent forgets the previous turn.",
            "Never let the model pass the tenant id as an argument; read it from context.",
        ],
        interview=[
            "create_agent is a small, production-ready loop; extend it with middleware before writing a graph.",
            "Context is per-run and trusted; state is per-thread and model-visible.",
        ],
    ),
    9: dict(
        excerpts=["cap_turns", "audit_log", "tiered_prompt"],
        mermaid="flowchart LR\n  in[messages] --> pii[PII redaction]\n  pii --> cap[before_model cap<br/>jump_to end]\n  cap --> dp[dynamic prompt]\n  dp --> m[model + retry]\n  m --> hitl[HITL on credit]\n  hitl --> tools[tools + retry,<br/>call limit, audit]",
        how=[
            "Each compliance requirement is one middleware: PII redaction, a turn cap using `jump_to`, a tier-based prompt, model and tool retry, a tool call limit, an audit wrapper, HITL on credits, and summarisation.",
            "The run shows which middleware fired for each request.",
        ],
        gotchas=[
            "Middleware order matters: redact before anything logs or summarises.",
            "Async agents need middleware with async hooks (`awrap_tool_call`).",
        ],
        interview=[
            "Middleware keeps cross-cutting controls out of business tools.",
            "Built-in middleware covers most compliance asks; custom hooks cover the rest.",
        ],
    ),
    10: dict(
        excerpts=["build_store", "evaluate", "retriever_tool"],
        mermaid="flowchart LR\n  md[guideline files] --> sp[splitter]\n  sp --> e[embeddings]\n  e --> vs[(vector store)]\n  vs --> r[retriever]\n  r --> ev[recall@k, MRR]\n  r --> tool[retriever as @tool] --> agent",
        how=[
            "Guidelines are loaded, split with overlap, embedded and stored; the retriever is measured on labelled questions before any model is involved.",
            "The retriever is then wrapped as a tool so the agent decides when to search, and the answer names its source.",
        ],
        gotchas=[
            "Measure retrieval separately; a good model cannot fix missing chunks.",
            "The offline embeddings are lexical hashes, so scores here are not representative of real embedding models.",
        ],
        interview=[
            "Agentic RAG lets the agent skip retrieval when it is not needed and search again when it is.",
            "Keep metadata (source, section) on chunks so answers can cite.",
        ],
    ),
    11: dict(
        excerpts=["vitals", "insurance", "triage", "build"],
        mermaid="flowchart LR\n  S((start)) --> v[vitals] & i[insurance]\n  v & i --> t[triage]\n  t --> E((end))",
        how=[
            "Nodes are plain functions that return partial state updates.",
            "Vitals and insurance run in the same super-step; triage waits for both.",
            "State history shows one checkpoint per super-step.",
        ],
        gotchas=["Two parallel nodes writing the same key need a reducer.", "A node returning the whole state can overwrite a sibling's update."],
        interview=[
            "Think in super-steps: everything scheduled together runs together, then state is merged and saved.",
            "Checkpoints per step are what make HITL and time travel possible.",
        ],
    ),
    12: dict(
        excerpts=["union", "Basket", "apply_promos"],
        mermaid="flowchart LR\n  S((start)) --> a[picker_a] & b[picker_b]\n  a & b -->|union reducer| promo[apply_promos]\n  promo --> E((end))",
        how=[
            "`add_messages` merges by id and supports `RemoveMessage`; `operator.add` accumulates; keys without reducers are overwritten.",
            "A custom union reducer combines parallel pickers without duplicates; `Overwrite` resets a reducer-managed list at checkout.",
        ],
        gotchas=["Appending reducers grow across turns on the same thread.", "Parallel writes to a key without a reducer raise an error."],
        interview=[
            "Reducers are the concurrency model of LangGraph state.",
            "Choose the reducer per key, based on how concurrent and repeated writes should combine.",
        ],
    ),
    13: dict(
        excerpts=["build_by_hand"],
        mermaid="flowchart LR\n  S((start)) --> m[model]\n  m -->|tools_condition| t[ToolNode]\n  t --> m\n  m -->|no tool calls| E((end))",
        how=[
            "A model node with `bind_tools`, a `ToolNode`, `tools_condition` and an edge back form the ReAct loop.",
            "The same questions run through `create_agent`; the tool calls and answers match.",
        ],
        gotchas=[
            "Forgetting the edge from tools back to the model ends the run after the first tool call.",
            "Bind tools to the model and register the same tools in ToolNode.",
        ],
        interview=["create_agent is this loop plus middleware hooks.", "Build by hand when you need extra nodes in the loop."],
    ),
    14: dict(
        excerpts=["route", "investigate", "fan_out"],
        mermaid="flowchart LR\n  S((start)) -->|route| sr[sanctions_review] & inv[investigate] & ar[auto_repair]\n  inv -->|Command goto| tr[treasury] & ar\n  P((pack)) -->|Send per account| sum[summarise]\n  sum --> comb[combine]",
        how=[
            "A router function with `add_conditional_edges` sends sanctions hits to review and routes the rest by amount.",
            "`investigate` returns `Command(update=..., goto=...)`, recording its finding and choosing treasury or auto-repair in one step.",
            "`Send` maps one summarise task per account and a reducer combines the results.",
        ],
        gotchas=[
            "Do not combine a static edge with Command routing from the same node (see section 23).",
            "Type the Command destinations so the graph drawing is correct.",
        ],
        interview=["Use one routing mechanism per node.", "Send is LangGraph's map-reduce: the fan-out width is decided at runtime."],
    ),
    15: dict(
        excerpts=["sqlite_restart_demo", "postgres_demo"],
        mermaid="flowchart LR\n  S((start)) --> i[intake] --> e[evidence] --> d[decide] --> E((end))\n  i & e & d -.checkpoint.-> db[(InMemory / SQLite / Postgres)]",
        how=[
            "Each step is checkpointed under the case's `thread_id`; a new process with a new SQLite connection continues the case.",
            "`get_state_history` gives auditors every intermediate state; `update_state` corrects a field and the run is replayed from that checkpoint as a fork.",
            "With `DATABASE_URL` set, the same graph runs on `PostgresSaver` (CI uses a Postgres service container).",
        ],
        gotchas=["Call `setup()` once on SQLite/Postgres savers to create tables.", "InMemorySaver is lost on restart; use it only in tests."],
        interview=["Durable execution is a checkpointer plus a thread id.", "Time travel is reading history and resuming from an older checkpoint."],
    ),
    16: dict(
        excerpts=["build"],
        mermaid="flowchart LR\n  S((start)) --> x[extract] --> r[underwriter_review<br/>interrupt]\n  r --> w[post_conditions<br/>writes to LOS] --> E((end))",
        how=[
            "`interrupt()` pauses with a payload describing the proposed conditions; the result has `__interrupt__`.",
            "`Command(resume=...)` continues with the underwriter's decision.",
            "Approved or edited conditions are posted by `post_conditions`; a rejection posts nothing. The buggy variant posts to the LOS before its interrupt, and posts twice.",
        ],
        gotchas=["A resumed node runs again from its first line.", "Without a checkpointer an interrupt cannot be resumed."],
        interview=[
            "Put side effects after the interrupt, or make them idempotent.",
            "HITL is a checkpoint plus a resume value, so the human can answer hours later.",
        ],
    ),
    17: dict(
        excerpts=["make_store", "remember", "recall_preferences"],
        mermaid="flowchart LR\n  t1[thread 1] -->|remember| st[(store<br/>namespace per patient)]\n  t2[thread 2, weeks later] -->|search| st",
        how=[
            "An `InMemoryStore` with an embedding index stores preferences under a namespace per patient.",
            "Nodes and tools reach it through the runtime; a new thread recalls the preferences by meaning.",
            "A second patient's search returns nothing from the first patient's namespace.",
        ],
        gotchas=[
            "Checkpointer memory is per thread; store memory is across threads.",
            "Scope namespaces by user from trusted context, never from model output.",
        ],
        interview=["Short-term memory is state; long-term memory is a store.", "Production stores are Postgres-backed with the same interface."],
    ),
    18: dict(
        excerpts=["track_order"],
        mermaid="flowchart LR\n  run[agent run] -->|updates| console[support console]\n  run -->|messages| ui[token stream]\n  tool[track_order] -->|custom| ui",
        how=[
            "One run is streamed with several modes; each event is tagged with its mode.",
            "The tool emits progress through `get_stream_writer`, which arrives as `custom` events.",
        ],
        gotchas=[
            "Token streaming needs a model that streams; the scripted model yields chunks.",
            "With subgraphs, pass `subgraphs=True` to see their events.",
        ],
        interview=[
            "Streaming is about perceived latency and transparency.",
            "Use `updates` for logs, `messages` for chat UIs, `custom` for progress.",
        ],
    ),
    19: dict(
        excerpts=["transfer_to_billing", "fraud_subgraph", "build"],
        mermaid="flowchart TD\n  S((start)) --> sup[supervisor<br/>structured router]\n  sup --> c[claims_agent] & p[policy_agent] & b[billing_agent]\n  c -->|Command.PARENT handoff| b\n  F((separate parent)) --> f[fraud_check subgraph<br/>collect, score: private state]",
        how=[
            "A structured-output supervisor picks a specialist; each specialist is a compiled agent added as a node.",
            "The claims agent hands off to billing with `Command(goto=..., graph=Command.PARENT)`.",
            "The fraud subgraph has its own state schema; only its verdict reaches the parent.",
        ],
        gotchas=[
            "Handoffs need the destination declared on the parent graph.",
            "Shared keys between parent and subgraph are passed through; private keys are not.",
        ],
        interview=[
            "Use multi-agent when specialists need different tools or prompts; otherwise one agent is simpler.",
            "Subgraphs give encapsulation, like functions.",
        ],
    ),
    20: dict(
        excerpts=["fetch_loan", "nightly_digest"],
        mermaid="flowchart LR\n  e[@entrypoint nightly_digest] --> f1[@task fetch_loan] & f2[@task fetch_loan]\n  f1 & f2 --> r[@task recommend]\n  r --> i[interrupt: manager approval]\n  i --> d[digest]",
        how=[
            "`@task` calls return futures, so fetches run in parallel.",
            "The workflow interrupts for approval; on resume, finished tasks come from the checkpoint and are not re-run.",
            "`entrypoint.final` returns a value while saving different state.",
        ],
        gotchas=["Code outside tasks re-runs on resume; keep side effects in tasks.", "The functional API needs a checkpointer for interrupts."],
        interview=["The Functional API gives durable execution without a graph.", "Tasks are the unit of checkpointing."],
    ),
    21: dict(
        excerpts=["rules_engine", "traced", "leaks"],
        mermaid="flowchart TD\n  r[explain_alert @traceable] --> rules[rules_engine @traceable]\n  r --> prof[customer_profile @traceable]\n  r --> agent[agent run<br/>model + tool spans]\n  agent -.masked payloads.-> c[(LangSmith or offline recorder)]",
        how=[
            "Plain bank code is traced with `@traceable` alongside agent spans, tagged by tenant and alert.",
            "Masking per function (`process_inputs`) misses spans created by the agent; masking on the client (`hide_inputs`/`hide_outputs`) covers every span. The output counts leaking spans for both.",
            "Offline, `OfflineLangSmithClient` records the exact payloads; with both LangSmith switches set, the real client sends them.",
        ],
        gotchas=[
            "`LANGSMITH_TRACING=true` without an API key causes 401 errors at runtime; this repo checks both.",
            "Mask on the client, not per function.",
        ],
        interview=["Turn tracing on before debugging, not after.", "Traces become datasets: interesting runs are added as eval examples."],
    ),
    22: dict(
        excerpts=["load_graph"],
        mermaid="flowchart LR\n  cfg[langgraph.json] --> dev[langgraph dev<br/>local server]\n  cfg --> build[langgraph build / dockerfile]\n  build --> img[image] --> host{managed or self-host}\n  sdk[SDK: threads, runs, crons] --> dev",
        how=[
            "`langgraph.json` registers the graphs, dependencies and env file; the config is validated and a Dockerfile is generated offline.",
            "The server graph is compiled without a checkpointer because the Agent Server supplies one.",
            "CI starts `langgraph dev` and calls it with the SDK (`scripts/agent_server_smoke.py`). Nothing is deployed.",
        ],
        gotchas=[
            "Compiling the server graph with your own checkpointer conflicts with the server's persistence.",
            "Self-hosting needs Postgres, Redis and a license or LangSmith key; see docs/deployment.md.",
        ],
        interview=[
            "The Agent Server adds threads, runs, background jobs, crons and streaming over HTTP.",
            "Managed versus self-host is a data-residency and operations trade-off.",
        ],
    ),
    23: dict(
        excerpts=["g3_broken", "g6_run"],
        mermaid="flowchart LR\n  b[broken case] -->|assert symptom| t[test]\n  f[fixed case] -->|assert fix| t",
        how=[
            "Each gotcha has a broken function that reproduces the symptom and a fixed function; the output table shows both.",
            "Tests assert both sides, so a library change in either behaviour is caught.",
        ],
        gotchas=[
            "See the table in the output: compile, thread ids, recursion limit, reducer growth, double routing, re-run after interrupt, checkpoint type allowlist."
        ],
        interview=[
            "Writing the failing case first proves you understand the cause.",
            "Most LangGraph bugs come from state merging and resume semantics.",
        ],
    ),
    24: dict(
        excerpts=["modern_run"],
        mermaid="flowchart LR\n  old[AgentExecutor + LLMChain +<br/>ConversationBufferMemory] -->|migrate| new[create_agent + LCEL +<br/>checkpointer]\n  old & new --> parity{same calls,<br/>answers, summary?}",
        how=[
            "The legacy bot (labelled LEGACY in `src/lcstack/legacy/fnol_bot.py`) and the migrated agent answer the same two turns.",
            "Tool calls, answers, the follow-up and the summary are compared; all four must match.",
        ],
        gotchas=["Memory moves from a memory object to `thread_id` on a checkpointer.", "Legacy classes need `langchain-classic` installed."],
        interview=[
            "Migrate behind a parity test, not by rewriting and hoping.",
            "Keep the legacy code until the parity test has run in production traffic.",
        ],
    ),
    25: dict(
        excerpts=["verify_map", "lint_source"],
        mermaid="flowchart LR\n  map[import map] -->|importlib| v[verified rows]\n  repos[agent repos] --> lint[AST lint] --> ci[CI fails on pre-1.0 imports]",
        how=[
            "Each row of the import map is imported from the installed packages and the symbols are counted.",
            "`lcstack lint-imports` parses Python files and flags pre-1.0 imports with the replacement; CI runs it on this repo.",
        ],
        gotchas=[
            "`langgraph.prebuilt.create_react_agent` is superseded by `langchain.agents.create_agent`.",
            "Old `langchain.chat_models` provider classes moved to integration packages.",
        ],
        interview=["Verify the map against installed versions, not memory.", "An import linter is a cheap guard during migrations."],
    ),
}
