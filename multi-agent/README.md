# multi-agent mechanisms

The actual hooks, wrappers, and crons behind [`docs/multi-agent.md`](../docs/multi-agent.md) and
[`docs/context-management.md`](../docs/context-management.md). The docs tell the story; this is the code.

Each is **failure-driven** — it exists because something broke — and each is sanitized to generic paths
and actors. They are examples to adapt, not a drop-in framework: read one, understand the failure it
addresses, and port the idea.

| File | Type | Addresses |
|------|------|-----------|
| `git-guard` | PATH wrapper for `git` | Agents run as root, repo owned by a user → destructive git wiped shared history. Redirects to the owner; blocks destructive verbs in the shared repo. |
| `briefing-watchman.sh` | `UserPromptSubmit` hook | A briefing nobody re-reads goes stale; an inbox nobody is told to read is not a channel. Resolves the agent by name, injects a changed briefing, pings only hanging inbox items every turn, and shows deltas of shared files. |

More mechanisms (atomic inbox writer, tool-output trimmer, tool-policy redirect)
are being added here as they're sanitized.

## A note on trust

These run on every prompt or tool call, or on a schedule. Read the source before installing any of them —
that's the whole point of shipping the code, not just the description. None make network calls; all fail
open (exit 0) unless they are *deliberately* blocking (exit 2 / non-zero with a message).
