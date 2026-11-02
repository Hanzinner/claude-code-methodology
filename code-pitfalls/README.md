# code-pitfalls

Technical mistakes already paid for, one file per technology. Behavioral mistakes
(how an agent decided, communicated, verified) go in the mistakes journal
([`docs/mistakes-journal.md`](../docs/mistakes-journal.md)); this is for the
technical lesson that another agent — on any project — would step on too.

`hooks/code-pitfalls-hint.py` shows the **headings** of the matching file right
before an agent edits code of that kind, so a lesson is in front of it at the
moment it matters, not in a postmortem nobody re-reads.

**Stepped on a new one?** Append it at the bottom of the matching file — only a
**confirmed** fix, not a hypothesis:

```
### <short name>
- **Symptom:** what you see (one line)
- **Why:** the causal mechanism (one or two lines)
- **Right way:** the exact action or command (one or two lines)
- **Seen:** how many times, how many agents
```

Already there? Don't duplicate — bump its "Seen" count. A repeat is a candidate for
a mechanism (a hook or a gate), not for a louder sentence.

| File | About |
|---|---|
| `verification.md` | proof of execution, instruments that lie |
| `shell.md` | bash, process killing, `set -e`, `sleep` vs events, permissions |
| `concurrency.md` | shared files, locks, TTLs |
| `hooks.md` | Claude Code hooks and gates |

These are seeds taken from a larger private set (~220 lessons as of November 2026). Grow your own.
