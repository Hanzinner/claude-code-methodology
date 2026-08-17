# Mission control: a panel over live agents

A web panel to steer a running swarm — without launching anything. The insight is that a `claude -p`
call is a **cold start** (a fresh context, several percent of quota); an agent that's already alive and
*listening* can be steered for the cost of appending a line to a file. So the whole panel is built around
a **cheap push into a live session** instead of an expensive spawn.

This is a pattern, not shipped code — the reference implementation is one bespoke server wired to a
specific project. The ideas below are what transfer.

## The channel

- **A button only writes a file.** It appends one line to `<channel>/<agent>.cmd`. No process is ever
  launched. The agent is already running a `tail -F` on that file and reacts to new lines.
- **Plain text, not JSON.** The reader is an LLM; a human-readable line reads fine in `tail` *and* in
  `git`. And the instruction is **self-sufficient** — the agent doesn't need to know the panel exists:

  ```
  [2026-01-02 14:30] PANEL ▶ Do ONE next item from your todo and stop (a single pulse).
  [2026-01-02 14:30] PANEL ▶▶ Run your built-in /loop. Limit: <...>. Before each iteration check that
                              <path>.flag still exists — if it's gone, that's the stop-cord.
  [2026-01-02 14:30] PANEL 🛑 STOP: finish the current iteration and stop.
  ```

- **Don't reinvent loops.** "Run continuously" just tells the agent to start its **built-in loop**; the
  **stop-cord is a flag file** — when it disappears, the agent ends the loop. No process management.

## Everything is counted from the outside

The panel never trusts an agent's self-report. Every status is an external measurement (see
[`measurement-and-proof.md`](measurement-and-proof.md)):

- **Subscribed?** — proof of execution: a live `tail -F` in `ps`, not a declaration. Steer-buttons are
  disabled for an agent with no live tail.
- **Active?** — the youngest file mtime in the agent's folder ("moved 3 min ago").
- **In a loop?** — commits authored by that agent since the loop started.
- **What stage?** — only actual signals (`ps` + `/proc/<pid>/cwd` + mtimes + `git`), attributed by the
  agent's worktree. **Uncertain attribution → show no stage** rather than a guessed one.

## The human's click is a mechanism, not a note

A "done ✓" button on a task doesn't record the completion in some side state — it **edits the source
file** the task lives in (`[x]` + a marker, `flock` + atomic write). Human confirmation becomes a
mechanical edit of the truth, not a memory that can drift. (Same spirit as everything in
[`multi-agent.md`](multi-agent.md): state lives in the file, not in a claim.)

## Keeping listeners alive cheaply

Listening costs **zero tokens** — a `tail -F` just blocks. So a watchdog cron checks each channel for a
live tail; if none, it raises a listener session (e.g. in `tmux`) that re-subscribes. You pay only the
cold start on a *re-raise*, not for standing by. A quota guard refuses to raise anything once quota is
nearly spent — don't spend the last of the budget keeping idle listeners warm.

## Two lessons paid for

- **Ownership is a mechanism, not a one-off `chown`.** When files are written by one user (agents as
  root) and the panel runs as another, a single `chown` goes stale the moment a new file appears. A
  per-minute cron that realigns ownership is the fix — the same "remove the gap, don't guard it" move as
  the [git wrapper](../multi-agent/git-guard).
- **Test against a throwaway channel.** Test pulses (▶/▶▶/🛑) once went into a *live* subscribed channel.
  The effect was harmless (a final 🛑), but the rule stands: create a separate test channel, never poke
  the production one.
