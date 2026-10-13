# ADR 0003: Guardrails as agent middleware plus graph nodes

**Status:** accepted

**Context.** Injection can arrive in the customer message, tool output or retrieved text; risky tools must
need a human; each agent must stay within its tools.

**Decision.** Input screening and output validation are graph nodes; tool-output screening, allowlists,
HITL and PII masking are middleware on every specialist, with sync and async hooks.

**Consequences.** Controls are uniform and testable per layer; the eval compares guarded and unguarded
configurations to show what each layer buys.
