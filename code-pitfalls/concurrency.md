# concurrency

### Read-modify-write of a shared file without a lock → lost update
- **Symptom:** messages vanish from an inbox, headers torn, sections duplicated; the sender saw `✓`, the recipient sees nothing.
- **Why:** agents and crons write the same file at once; "read → change → write back" erases whatever landed between the read and the write. A lock held by only one of the writers saves nothing.
- **Right way:** one sanctioned writer (e.g. `multi-agent/inbox-post.sh`): `flock` on a separate `.lock` file (not the file itself — `mv` swaps its inode), then validate by reading back from disk. Never `cat >>` or a bare editor write.
- **Seen:** 7+ times across 4 agents.

### A lock the other side can't see; a lock without a TTL
- **Symptom:** two agents took the same version number; or finished work waits for hours behind someone else's lock.
- **Why:** the lock lived in a different directory than the reader checked; a lock with no TTL and no takeover rule deadlocks the polite agent.
- **Right way:** one canonical lock path, checked against the code that reads it; every claim/lock carries a TTL and a takeover rule. Better: a design with no shared state (a queue).
