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

| File | Lessons | About |
|---|---|---|
| `shell.md` | 34 | bash, process killing, `set -e`, `sleep` vs events, permissions, cron |
| `python.md` | 30 | text edits by script, encodings, subprocesses, migrations |
| `git.md` | 27 | shared working trees, wrappers, hooks, what a commit really takes |
| `web.md` | 33 | small stdlib sites, JS patches, layout checks, other people's sites |
| `verification.md` | 28 | proof of execution, instruments that lie |
| `hooks.md` | 20 | Claude Code hooks and gates |
| `concurrency.md` | 12 | shared files, locks, TTLs, connection pools |
| `services.md` | 16 | systemd, cron, permissions of service users |
| `vm.md` | 19 | a Linux VM on a Windows Hyper-V host |
| `windows.md` | 18 | PowerShell and Windows over SSH |
| `android.md` | 30 | automating Android apps over adb |

This is the private set as of November 2026 with private context removed (a few near-duplicates merged). Grow your own.
