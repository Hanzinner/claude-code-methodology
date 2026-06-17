---
name: feedback-example
description: Example feedback-type memory — a correction with Why and How to apply.
metadata:
  type: feedback
---

# Integration tests must hit a real database (example)

**Rule:** Don't mock the database in integration tests. Spin up a real instance (Docker, test container, in-memory PG) and run against it.

**Why:** Last quarter, mocked tests passed but the production migration failed because the mock didn't reproduce a foreign-key cascade Postgres performs at the engine level. The bug existed for two weeks before someone noticed. We're not paying that cost again.

**How to apply:** When writing tests under `tests/integration/`, default to a real DB via the `db_fixture` test helper. Mocking is only acceptable in `tests/unit/`, and even there, prefer in-memory PG over mocks if the code touches SQL.
