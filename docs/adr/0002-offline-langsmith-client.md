# ADR 0002: Record LangSmith payloads offline instead of mocking tracing

**Status:** accepted

**Context.** `tracing_context(enabled="local")` still attempted uploads (401). Tests must prove masking and
run-tree shape without a network.

**Decision.** `OfflineLangSmithClient` subclasses `langsmith.Client` and records `create_run`/`update_run`
payloads, applying `hide_inputs`/`hide_outputs` exactly like the real client. Tracing is on only when both
`LANGSMITH_TRACING` and `LANGSMITH_API_KEY` are set; tests block sockets.

**Consequences.** The same code sends to LangSmith when an account is configured. The recorder depends on
SDK internals and is pinned with the SDK version.
