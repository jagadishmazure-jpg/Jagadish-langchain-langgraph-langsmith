# ADR 0001: A scripted chat model so everything runs without keys

**Status:** accepted

**Context.** The repository must run end to end in CI and on a laptop with no API keys, and its documented
output must be reproducible so doc drift can be checked.

**Decision.** `ScriptedChatModel`, a real `BaseChatModel` driven by playbooks, emits tool calls, structured
output and streamed chunks. `LCSTACK_MODEL` switches to Azure OpenAI (Entra ID token, no key) or any
`provider:model` string.

**Consequences.** Every LangChain/LangGraph code path runs for real (middleware, ToolNode, checkpointing);
only the text generation is scripted. Evaluation numbers measure the pipeline and guards, not model
quality, and say so.
