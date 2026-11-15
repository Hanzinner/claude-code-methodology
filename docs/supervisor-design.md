# Supervisor: checking that the machinery does its job

Design behind `scripts/supervisor.py` and `config/supervisor-checks.template.json`, plus the nightly read-only memory pass (`scripts/memory_consolidation.sh`). Ideas borrowed from two places: Erlang/OTP supervision trees ("let it crash", but cap the restarts) and sleep-time consolidation (do memory housekeeping while nobody is working).

## Why

A swarm already has restarts: every service is `Restart=on-failure`. What it did not have was a check that the restarted thing *does work*, and a signal for when restarts stop helping. "The process is alive" is not "it works". Three incidents:

- **A messaging bot sat dead for a month** (825 restarts). systemd said `active`, the restart policy faithfully restarted it, and it never received a single message. A battery watcher ran for the same month with `exit 0` and no connection to the laptop it was watching. Nobody knew.
- **A hook was dead for 33 days** (missing `+x`). A guard was recorded as "mechanized" in the mistakes journal but was never registered in `settings.json`. Nothing noticed either.
- **A weekly review job saw 39 entries instead of 52 for a month.** It ran, it exited cleanly, and it was blind to a third of its input.

Common cause: the restart exists, the verification of the *result* does not.

## A. The supervisor

Cron every 15 minutes. Ships as `scripts/supervisor.py`; the registry template is `config/supervisor-checks.template.json` (`supervisor.py --init <template>` copies it to `<state>/checks.json`; `install.sh` does this and adds the cron line).

### Registry: one entry per mechanism, a functional check each

The engine is generic, the registry is the machine's data. Check kinds: `http`, `tcp`, `cmd`, `fresh` (file age), `journal` (a fresh line in `journalctl`), `hooks`, `system`. Per entry: `severity` (`human` or `infra`), `owner` (agent name, list, or empty = no letter), optional `service`, `max_restarts_hour`, `grace_min`, `only_if_exists`, `enabled`, `note`.

What a check should look at, rather than "is the process up":

| Mechanism | Functional check |
|---|---|
| bot / chat service | an API call answers within seconds **and** the restart counter is not growing |
| web panels | HTTP 200 on their own page |
| watchers | a fresh "I saw the object" line in their log (a blind watcher is a dead one) |
| cron jobs | a fresh success line in the log, within period x 1.5 |
| per-message hooks | fired in the last 24 h, **if** the human sent messages in that window (no sessions is not an alarm) |
| rare hooks | only "file exists, executable, registered in settings" (`kind: hooks`) |
| the machine itself | `/dev/null` is a device, free disk above a threshold (`kind: system`) |

In this repo: the template ships hooks/registry lint, hooks-do-not-time-out, the watchman heartbeat, reminders, releaser, a weekly review log, daily report freshness, quota status and a few stats-file freshness checks. Checks for your own services (a bot, a panel) you add yourself; none ship.

Two lessons baked into the registry:

- A `fresh` check on a `*.log` is suspect, because a log is also written on failures. `scripts/checks_lint.py` (run as the first registry entry) requires a `fresh_ok` reason for those, so a check cannot quietly measure "something wrote a line" instead of "it worked".
- A check that needs a source file which is not there yet is skipped (`only_if_exists`) rather than red.

### One run

1. Run every check, each with a timeout. A crash in one check never takes the run down.
2. A failed check on an entry with a `service` -> `systemctl restart`, then re-check. Entries can ask for a second try before the restart (`recheck_before_restart_s`), because a short outage of somebody else's network is not cured by a restart, and the restart cuts the service's work. `restart_only_if_dead` restarts only if the unit is really not active.
3. **Escalate instead of restarting forever.** At `max_restarts_hour` (default 3) restarts in an hour, ours or systemd's own (`NRestarts` growth), restarts stop and the owner gets a letter. 825 restarts is exactly what should have been stopped at the third.
4. Red check -> a letter into the owner agent's inbox via `scripts/inbox_post.sh`. Dedup: the same alarm is not re-sent for 6 h, nor while the previous copy still sits unread in the owner's inbox.
5. `severity: human` (the human sees the consequence with their own hands: a bot, a panel) and it did not heal itself -> additionally a one-line flag for every live session, shown once on the next prompt by `hooks/surface-flags.sh`. The text says what is down and what was already tried, with no technical detail. When it recovers, a "works again" flag follows; otherwise the human stays convinced it is still broken (a bot was back in 40 s and the human thought it dead for two days).

In the original design the human was messaged directly in a chat app. The shipped engine does not do that: it flags through the agent sessions. Pushing to a chat app is not in this repo.

### "The check is broken" is not "the object is down"

A `cmd` that exits 126/127 (command missing) or 3 (UNKNOWN, the Nagios convention: could not measure), prints a traceback, or raises inside the engine is classified as a broken instrument. No restart, no human flag; one letter to the infra agent (`CCM_INFRA_AGENT`, else the owner). Origin: two checks against the local network reported "outage" for 17 hours when it was the measuring that could not run.

### Silence after downtime

Age checks ("nothing updated for N minutes") all go red at once after the machine was off. The engine measures its own gap between runs, not uptime (a paused VM keeps its uptime). A gap over `SUPERVISOR_GAP_MIN` (20 minutes) is downtime, and age checks stay quiet until their own limit has passed since the resume (`grace_min` overrides). Paused projects (`CCM_SUPERVISOR_PAUSED`) are skipped entirely.

### Who watches the supervisor

Every run writes `<state>/heartbeat` (epoch), `summary.json` and a log line.

- `hooks/briefing-watchman.sh` reads the heartbeat file named by `CCM_SUPERVISOR_HEARTBEAT` and warns the agent when it is stale. The supervisor in turn has a check that the watchman's own heartbeat is fresh while chats are active.
- `scripts/token_daily_report.py` adds one line to the daily report: "supervisor: ok (N checks)", "N problems" or "silent for N h".

They watch each other. If both die at once, the daily report is missing, which is visible.

### Done when (how it was verified)

Stop a test service and see it restarted within 15 minutes; break its check four times and see restarts stop and a letter arrive; make the heartbeat old and see the watchman show it. Tests live under `tests/`.

## B. Nightly memory consolidation

`scripts/memory_consolidation.sh`, opt-in (`install.sh --with-consolidation`, because it spends model quota). One fresh `claude -p` run per day on a cheaper model with tools limited to Read, Grep, Glob. **It reads and writes a report; it never edits memory.** The md5 of the memory directory is taken before and after; a difference is logged and flagged (a read-only run cannot change memory, so either someone wrote in parallel or the tool list leaks). The human decided that feedback must not be merged into memory without them, and an automated writer is also a memory-poisoning path.

What it looks for: contradictions between memory files, library and briefings; dated claims ("current", "live") older than 30 days in files that describe mechanisms; duplicate or overlapping memory files (proposes a merge, does not merge); broken links (`scripts/broken_links.py`); journal entries without a class; a fact repeated across 3+ days of the episodic log with no memory file.

When it runs: the original spec said "the human quiet for 3 hours and quota has headroom". That condition never happened on a live machine, because every such pause was a machine that was off. The shipped gate (cron hourly, the script decides): not run today yet, and (the human quiet for 45 minutes, or yesterday was missed too, or it is 23:00 or later). The quota is not gated, since a quota meter can be wrong; the cost control is the cheaper model and once a day.

Output: `<CCM_CONSOLIDATION_DIR>/YYYY-MM-DD.md` and one letter to `CCM_CONSOLIDATION_KEEPER`. The keeper handles the mechanical findings itself (links, dated facts verifiable by code) and brings the human only taste and intent questions as one line. Counters, journal classes, formats and "should I recount" are plumbing, not questions for the human: the first run carried "recount class 2?" to the human and was itself wrong about the count.

## Unsure / not in this repo

- Direct chat-app notification of the human (see above).
- Checks for specific services such as a bot or panels: the engine supports them (`http`, `journal`, `service`), the template does not include them.
- The reconciliation "every mechanism in the library must have a registry entry" was ordered separately; `scripts/library_check.py` exists, but whether it covers the supervisor registry was not verified here.
