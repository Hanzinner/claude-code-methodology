# multi-agent examples

Two hand-made mechanisms that `install.sh` does **not** install yet. Read one, understand the failure it
addresses, and port the idea.

The swarm mechanisms that used to live here are now installed by `install.sh` (layer 2): the inbox writer is
`scripts/inbox_post.sh`, the briefing watchman is `hooks/briefing-watchman.sh`, the git wrapper is `bin/git-guard`
(with `--with-git-guard`). See [`hooks/README.md`](../hooks/README.md) and [`scripts/README.md`](../scripts/README.md).

| File | Type | Addresses |
|------|------|-----------|
| `session-hygiene.py` | cron | Long chats bloat. Trims old tool outputs from large, inactive session files (cutting *both* copies the harness stores), atomic with a `-cut.jsonl` rollback and a zero-trust "no fresh backup → refuse" interlock. |
| `tool-redirect.sh` | `PreToolUse` hook | Move the whole fleet from one tool to another with no briefing edits: deny the tool and put the instruction to use the right one in the denial reason. The agent reads it and retries correctly. |

## A note on trust

These run on every prompt or tool call, or on a schedule. Read the source before installing any of them —
that's the whole point of shipping the code, not just the description. None make network calls; all fail
open (exit 0) unless they are *deliberately* blocking (exit 2 / non-zero with a message).
