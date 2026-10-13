# ADR 0004: A regression gate with tolerances and hard safety floors

**Status:** accepted

**Context.** Prompt or model changes can silently reduce quality or safety.

**Decision.** `lcstack gate` compares the production configuration with `evals/baseline.json` (recorded from
the first real offline run) with a 0.02 tolerance, requires `no_pii_leak` and `injection_safe` at 1.0, and
runs all 25 scenarios. CI runs it on every push.

**Consequences.** Raising the baseline is an explicit, reviewed change. Known router misses stay in the
dataset so improvements show up as real gains.
