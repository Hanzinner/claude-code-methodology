# session-hygiene - keep long chats loadable

Claude Code stores every tool output of a session twice in the session file (`~/.claude/projects/<project>/<session>.jsonl`):
as the `tool_result` the model saw and as the `toolUseResult` field next to it. In a chat that lives for weeks this
grows to hundreds of MB, and the chat gets slow to open and to resume. Most of it is old command output nobody reads.

`session-hygiene.py` cuts those two copies in old records of large, inactive sessions and keeps everything it cut.

## What it never touches

* conversation text, thinking, tool inputs (what the agent ran), attachments the human pasted;
* the newest 150 user/assistant records of a session;
* a session written to in the last hour (it may be open), or one under 5 MB;
* a line that was already broken (it stays byte-identical);
* **any session the nightly chat backup does not hold exactly as it is now** (next section).

What it cuts goes to `<session>-cut.jsonl` next to the session (written and flushed first), so every cut record can be
put back. The session itself is written to a temp file, every line re-parsed as JSON, then renamed over the original.

## The backup interlock

It runs only on top of the nightly chat copy that `install.sh` schedules by default (`scripts/backup-chats.sh`, 03:10,
`~/.claude-backups/<date>/home/...`):

* the newest day folder of that copy must be younger than 30 h - otherwise it changes nothing at all and exits 75
  ("not ready"; `bin/catchup-run` tries again the next hour);
* a session is trimmed only if that folder holds a copy with the same size and modification time - the session has not
  changed since it was copied. The untrimmed original therefore always exists in the backup.

## Install and run

`install.sh --with-session-hygiene` copies this folder to `<claude dir>/addons/session-hygiene/`, adds one crontab line
(`bin/catchup-run session_hygiene daily --after 4`: from 04:00, after the chat backup; a day missed while the machine
was off runs at the next start) and one supervisor check ("Session hygiene ran": red when the last run failed or the
last success is older than 36 working hours). No root. Off unless you pass the flag.

```
python3 addons/session-hygiene/session-hygiene.py --dry-run     # what it would cut, changes nothing
python3 addons/session-hygiene/session-hygiene.py FILE.jsonl    # only this session (the same checks apply)
```

Log: `~/.claude/cron-logs/session_hygiene.log`. Exit: 0 done · 1 a session could not be processed (ERROR/ABORT
line) · 75 no fresh chat backup.

To stop it: re-run install.sh without the flag (the crontab block is rewritten without the line). To undo a trim: the
backup folder of that night holds the session as it was; or put the records from `<session>-cut.jsonl` back by
`uuid` (`tool_results[].index` is the position in `message.content`).

## Test

`tests/session-hygiene-test.py`: a temp session root, a temp chat backup and HOME in a temp folder. No backup / a stale
backup / a session changed after the copy / an active session -> not one byte changed; a large old session with its
copy -> outputs cut, text, thinking, tool inputs, attachments and the broken line unchanged, `-cut.jsonl` restores every
record exactly; `--dry-run` changes nothing; an unreadable file -> rc 1.
