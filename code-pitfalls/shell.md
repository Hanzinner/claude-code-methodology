# shell

### `pkill -f` / `pgrep -f` matches your own shell
- **Symptom:** the command dies silently (exit 144/1, no output), or a wait loop `until ! pgrep -f X` hangs forever "seeing" a process that isn't there.
- **Why:** `-f` matches the full command line of ANY process — including the bash or ssh whose command line contains the pattern. The hunter becomes the target; over ssh, it kills its own session.
- **Right way:** kill your own process by PID (`PID=$!` → `kill "$PID"` in a `trap`). With no PID, put a character class in the pattern so it can't match itself: `pgrep -af '[q]emu-system'`.
- **Seen:** 8+ times across 6 agents — then mechanized as a gate.

### Silent death under `set -e` — the log is empty
- **Symptom:** a cron script "doesn't work" and its log says nothing; or it redoes the same work every tick.
- **Why:** `set -e` exits on the first non-zero code without a word — before your `log` line ever runs.
- **Right way:** `trap 'echo "ABORT: line $LINENO: $BASH_COMMAND" >>"$LOG"' ERR`; check up front for steps that may legitimately be a no-op.
- **Seen:** repeatedly; one case left a snapshot cron silently dead for 2 hours.

### A fixed pause racing an event of variable length
- **Symptom:** a "flake": occasional FAIL on a healthy system, truncated logs, the first bytes of a command eaten.
- **Why:** `sleep X` was tuned on one example; a change in scale (file size, load, cold start) makes the event longer than the pause. It's a race by construction.
- **Right way:** measure the event first; then wait for the EVENT with a deadline (a log marker, an echo, "saved"), derive the deadline from the size; a timeout is a real FAIL with the log tail, not a verdict.
- **Seen:** 6+ times (one instrument slept 1.2 s against an event of 0.44–1.98 s).

### A file created by a Write tool has no `+x`
- **Symptom:** a script registered as a direct call (hook, cron) gets `Permission denied` — and under a fail-open wrapper that's silent, for weeks.
- **Why:** editor/Write tools create `rw-r--r--`; your manual test `python3 script` works without `+x`, so it never catches it.
- **Right way:** `chmod +x` right after creating it; accept it with the same invocation production uses.
- **Seen:** one hook stayed dead for 33 days.
