---
name: project-example
description: Example project-type memory — current state of an active project with Why and How to apply.
metadata:
  type: project
---

# Project Acme — auth migration (example)

**State (as of 2026-MM-DD):** Phase 2 of 4. Auth tokens are now issued by the new service in shadow mode; the legacy service still owns reads. Cutover scheduled for the end of next month.

**Why this matters:** Driven by compliance — the legacy service stored session tokens in a way that fails the new SOC2 audit. Scope decisions should favor compliance over ergonomics; if a "nicer" design adds risk to the audit, drop it.

**How to apply:** Any PR touching `auth/` or `session/` should be reviewed against the migration plan in `docs/auth-migration.md`. New endpoints should integrate with the new service from day one — don't add to the legacy interface, even temporarily.

**Open loops:**
- Frontend SDK update (Marketing team owns) — blocked on design review
- Old session table cleanup — scheduled for two weeks after cutover

Related: [[feedback-example]] (test discipline applies here too — no mocking the auth DB).
