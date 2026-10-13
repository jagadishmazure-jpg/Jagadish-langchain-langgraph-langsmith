# ADR 0005: Test PostgresSaver against a CI service container

**Status:** accepted

**Context.** Production checkpoints live in Postgres; the development box has no Docker.

**Decision.** A `postgres:17` service container in CI; tests marked `postgres` run when `DATABASE_URL` is set
and skip otherwise. SQLite covers restart behaviour locally.

**Consequences.** Postgres behaviour is verified on every push without local infrastructure.
