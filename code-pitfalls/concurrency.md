# concurrency

### Read-modify-write of a shared file without a lock → lost update
- **Symptom:** messages vanish from an inbox, headers torn, sections duplicated; the sender saw `✓`, the recipient sees nothing.
- **Why:** agents and crons write the same file at once; "read → change → write back" erases whatever landed between the read and the write. A lock held by only one of the writers saves nothing.
- **Right way:** one sanctioned writer (e.g. `scripts/inbox_post.sh`) plus one for closing items: `flock` on a separate `.lock` file (not the file itself — `mv` swaps its inode), then validate by reading back from disk. Never `cat >>`, a bare Edit/Write, or your own python script.
- **Seen:** 7+ times across 4 agents.

### "Delivered" proven in the wrong place
- **Symptom:** the script answered `✓`, and the addressee doesn't see the message.
- **Why:** post-validation checked the tmp file BEFORE `mv` (it proves the file was assembled correctly, not that it SURVIVED); the message sat in the file but outside the section the addressee reads.
- **Right way:** prove delivery by reading from disk AFTER the write, in the section the recipient reads (`grep` between `## New` and `## Done`).
- **Seen:** once.

### An item without a marker is invisible to the mechanism
- **Symptom:** tasks quietly disappeared from a queue — not pinged, not counted.
- **Why:** after a write collision the items lost their `- [ ]`; the hook sees only lines with the marker. The recovery "the file is intact" didn't check structure.
- **Right way:** after repairing a shared file, validate its structure (a line in "New" without `- [ ]` that isn't a continuation = broken data); an item that can't be acted on (a condition, waiting) is never `- [ ]`, but `> ⏸ Condition: …`.
- **Seen:** 2 times.

### TOCTOU: check the state → minutes of work → act
- **Symptom:** took a number/resource another agent already held; "staged deletion" turned into a commit.
- **Why:** a state ("the lock is empty", "`git rm` is done") was taken for an event that holds by itself; between the check and the action are minutes, and live agents write to the same tree.
- **Right way:** check at the moment of action, and better — remove the shared state by design: everyone writes their own file (a queue of markers), one automaton assigns the number from tags.
- **Seen:** 2 times.

### A lock the other side can't see; a lock without a TTL
- **Symptom:** two agents took the same version number; or finished work waits for hours behind someone else's lock.
- **Why:** the lock lived in a different directory than the reader checked; a lock with no TTL and no takeover rule deadlocks the polite agent.
- **Right way:** one canonical lock path, checked against the code that reads it; every claim/lock carries a TTL and a takeover rule. Better: a design with no shared state (a queue).
- **Seen:** 3 times.

### Two readers of one stream
- **Symptom:** the channel answers wrongly but plausibly (a reply without the echo, a line torn in half) or the run hangs.
- **Why:** two consumers drain the same queue/socket (two "pumps" on one serial port; a second `recv()` next to a background reader thread), each taking part of the data. The mechanism was duplicated to avoid touching someone else's file.
- **Right way:** a stream has EXACTLY ONE reader; everyone else reads its buffer (the rig's log / an internal buffer). When a swarm rule pushes you to duplicate a mechanism — agree with the owner, don't route around.
- **Seen:** 2 times in a day (the core and the Python facade).

### Shared resources with the same name across work trees
- **Symptom:** BrokenPipe and zombie processes "every other time" — written off as a flake for a year.
- **Why:** the socket tag was taken from `basename(dirname(cwd))`; after a path reorganization all work trees got the same tag → one socket for everyone.
- **Right way:** tag sockets/temp files by tree/agent and verify that the tags really differ (`ls /tmp/*.sock` from two trees).
- **Seen:** once, a year-long one.

### "The newest file" in a swarm is a lottery
- **Symptom:** a script returned someone else's session as yours (a stranger's dialogue was nearly written into memory).
- **Why:** "the freshest `.jsonl` by mtime" is right for a single agent; in a swarm several sessions write within seconds.
- **Right way:** take your own context explicitly (`CLAUDE_CODE_SESSION_ID`); a fallback heuristic must shout to stderr. Revise any "newest / the only process / last log".
- **Seen:** once.

### Several entrances to one harm — N checks by agreement
- **Symptom:** a bug is "fixed" and reproduces through another path (the free-space check was in `create_file`, while `cp` went through `create_file_streamed`).
- **Why:** several functions lead to the same harm; the check was put in one of them.
- **Right way:** one choke-point through which all paths physically pass (one write function, one stream reader); or remove the way to err by the shape of the API.
- **Seen:** once.

### Migration: two coordination mechanisms alive at once
- **Symptom:** every agent diligently follows ITS rule and breaks another's (the releaser doesn't read the lock, while the lock is still alive).
- **Why:** the transition between mechanisms lasts days and there is no rule for "who is in charge during the transition".
- **Right way:** in a migration, an explicit rule for the transition period written in the script itself; declare the old mechanism dead out loud and remove it; after removal, `grep -rl "<old mechanic>"` across agent folders, projects and docs, and clean up the instructions.
- **Seen:** once.

### `flock file command` when the command itself takes `fcntl.flock` on the same file — waiting forever
- **Symptom:** an outer `flock data/.bake.lock python bake.py` holds the lock on one open of the file, and bake.py opens the file again and asks for the lock itself → it waits for itself (state S, wchan `locks_lock_inode_wait`, 0 % CPU). A bake hung for 5 min.
- **Why:** two independent open file descriptions on the same file conflict even within one process tree.
- **Right way:** if the script takes the lock itself, run it without an outer `flock`. The outer one is only for scripts that take no lock.
- **Seen:** once.

### FastAPI + SQLAlchemy + SQLite under load: the pool is smaller than the threads, a write on every page view
- **Symptom:** 50 buyers at an auction — 270 of 484 requests failed with `QueuePool limit of size 5 overflow 10 reached`, p95 5–6 s. pytest and e2e (one request at a time) were green.
- **Why:** (1) synchronous FastAPI endpoints run in a pool of 40 threads while the default SQLAlchemy pool is 5+10 connections: a thread waiting for a lock (an application-level lock) holds a connection, the rest wait 30 s and fail. (2) "Close the expired" ran an `UPDATE` on every GET — in SQLite that is a write lock until the end of the request, so page views queued one after another. (3) `synchronous=FULL` in WAL — 7.7 ms of fsync per commit under the bidding lock.
- **Right way (confirmed by measurement: 0 errors, p95 ≤ 614 ms):** `create_engine(pool_size=20, max_overflow=30)` (≥ the server's threads); before a bulk `UPDATE` a cheap `SELECT … LIMIT 1`, and `UPDATE` + commit only when there is something to change; SQLite `PRAGMA synchronous=NORMAL` (safe against corruption in WAL; on power loss the last commits may vanish); notifications go in the event's transaction, not a separate commit. Also found: two consecutive reads (bid history and participant numbers) saw different states — read first whatever must be the subset.
- **Make it impossible:** a load run as part of acceptance (a story with the condition "0 5xx, p95 < 1 s"); functional tests don't catch this.
- **Seen:** once.
