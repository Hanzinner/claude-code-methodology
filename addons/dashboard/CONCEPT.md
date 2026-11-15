# Concept: a control panel for a swarm of agents (not shipped)

`dashboard.py` is the read-only part. The system this repo came from runs a much larger "panel" (about 1300 lines,
one server file) that is tied to that one machine and is therefore described, not ported.

## Problem

Ten agents in ten tabs, several of them looping. The human needs (1) who is busy, idle or waiting for an answer,
(2) a way to nudge a specific agent without switching tabs, (3) a stop switch for loops, (4) the state of the
surrounding system (quota left, last releases, open stories) in the same place.

## How it works

* **Status = files written by hooks.** The hook on "tool just ran" writes WORKING; the hook on "turn finished" writes
  DONE or ASK (when the last reply contains an `ASK:` line). The agent is not trusted to report its own state - the
  harness observes it. A dashboard only reads the directory. That is what `dashboard.py` does.
* **Commands = append-only text files, one per agent.** A button appends a human-readable line
  (`[time] PANEL > do ONE next item from your todo and stop`) to `<channel dir>/<agent>.cmd`. The panel never starts a
  process: a cold `claude -p` per click is slow and loses context. The agent is already alive and listens with
  Claude Code's `Monitor` tool on `tail -n0 -F <agent>.cmd`; each new line arrives as a notification.
  The line is plain text because the reader is a language model and the file is also read by humans and `git log`.
* **Subscription is proven, not declared.** The panel shows a button as enabled only if a live `tail -F` on that file
  exists in the process list.
* **Loops have a stop-flag file.** "Run a loop" tells the agent to start Claude Code's built-in `/loop` and to check
  before every iteration that `<agent>.flag` exists; deleting the file is the stop switch. Limits (time, quota percent,
  "all done") are passed as text in the instruction.
* **Side panels** are computed by the server, not reported by agents: quota (a root cron copies a status file where the
  unprivileged server can read it), the first unchecked item of each agent's todo, the tails of the release log and
  git log.

## What a stranger would need to build it

1. The status hook (shipped: `hooks/agent-status.py`) and a place that identifies the agent per session
   (`~/.claude/agent-identity/<session_id>`, shipped with the watchman).
2. A small web server on localhost with an authenticating proxy in front, because it has write buttons.
3. A channel directory and a one-line bootstrap per tab: `Monitor(command="tail -n0 -F <channel>/<agent>.cmd", persistent=true)`.
4. The rule that **buttons only append text**; anything that starts a process is a different, riskier tool.
5. Staleness handling: a status file saying WORKING for hours is a dead session, not a busy one - show it as stale
   (the live system learned this when a stuck WORKING misled a coordinating agent for 13 hours).

Not shipped because the panel hard-codes this machine's agent names, folder layout, release queue, quota source and
network addresses; the pieces worth copying are the five ideas above.
