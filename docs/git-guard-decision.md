# Decision record: git-guard

Why `bin/git-guard` exists and why it is a mechanism instead of a rule. The short version of the
incident is in [multi-agent.md](multi-agent.md#2-mechanism-beats-agreement); this is the reasoning
behind the fix, and what the repo ships of it.

## Incident

A history-rewriting command (`filter-repo`) ran in the main shared repo and cut it from 808
commits to 125. Recovered from a `.git` backup taken 20 minutes earlier; nothing lost. Verified
after the fact, not taken from the author's report: history back to full length, no root-owned
files left in `.git`, the leaked token gone from the tree, and the ownership split confirmed
(repo owned by one user, every agent running as root).

The post-mortem was written by a different agent than the one that caused it. A team does not
investigate its own failure; that is a conflict of interest, and it also made the author's
unsoftened report usable as evidence.

## Findings

**1. It was not a rule violation. It was a rule nobody can avoid breaking.**
The repo belonged to one user; every agent ran as root, by construction. The written rule
("always run git as the owner") demanded perfect recall from every agent on every command, forever.
Statistically, someone was going to miss. Nobody is to blame; the possibility of the mistake had
to go.

**2. Two independent holes, and the cascade needed both.**
- Trigger: `dubious ownership` (root vs owner) made the clone fail.
- Amplifier: the command chain had no `set -euo pipefail`, so the failed `cd` did not stop it and
  `filter-repo` ran in the *current* directory, the main repo.

Fixing only one leaves the other. Fixing ownership leaves a chain that executes destructive steps
after a failure; fixing the chain leaves root breaking git in other ways.

**3. A destructive tool must never be able to aim at the shared repo.**
History rewriting belongs in a throw-away clone, and only after proving the clone exists. The
working directory is a fact to verify before the shot, not an assumption.

**4. The leaked secret was not the human's fault.** A token placed in an agent's own folder, the
natural place, was committed by the automatic snapshot job within about two minutes. The hole was
on the agent side: an agent asking for credentials must say up front where to put them
(outside the git-tracked workspace). Silence is a trap. Not in this repo as a hook; the repo ships
the detector, `bin/secret-scan`, and the snapshot job is `scripts/daily-git-snapshot.sh`.

**5. The snapshot cron caused two different incidents the same day.** It committed the secret,
and it committed someone's unverified work-in-progress, which then rode into another agent's
release. Same disease as release contention: automation competes with agents for a shared
resource (the git index) and nobody owns it. Remedy: cron does not commit code to the main
branch; it is a precondition of the release queue, tracked separately.

## Decision

**1. Remove the cause, do not guard it.** After the operator's remark that the root/owner split
"has shown up forever, since git existed here", the problem was reclassified from incident to
chronic structural gap. A block-and-scold hook would turn one accident into permanent friction
for every agent and every command, and a rule everyone must work around by hand loses regardless.
So: a transparent `git` wrapper first in PATH. If the caller is root and the target is inside the
shared workspace, it re-executes git as the owning user. Ownership is then always correct and
nobody has to remember anything.

**2. Block destructive verbs in the shared repo, for everyone.** The correct owner does not protect
against a shot into someone else's tree, so this stays even after the redirect. Blocked: `filter-repo`,
`reset --hard`, `gc --prune`, `branch -D`, forced pushes, `clean -f`, and the like. Allowed only in a
throw-away clone. Reads are untouched.

**3. Secrets live outside the tracked workspace**, and agents tell the operator where, in advance.

**4. Destructive operation = backup plus a proven working directory.** The `.git` backup made
20 minutes earlier is the only reason this was a report and not a catastrophe. That is a duty to
make explicit, not a good habit.

Principle extracted: a rule that needs everyone to remember it forever is a deferred outage;
a mechanism beats an agreement.

## What it turned into: shipped vs not

| Piece | Status |
|---|---|
| Blocking wrapper, `bin/git-guard` | Shipped. Exit code 88 on a block. |
| Installer, `scripts/setup-git-guard.sh` | Shipped. User-scope symlink `git` -> the wrapper in a PATH directory (default `~/.local/bin`), `--system` for `/usr/local/bin`, `--rc-file`, `--uninstall`, `--dry-run`. Not run by default. |
| Tests, `tests/git-guard-test.sh`, `tests/git-guard-effects-test.sh` | Shipped. |
| Owner redirect (`sudo -u <owner> git`, with `GIT_*`/`EDITOR`/`VISUAL`/`PAGER` forwarded) | **Not in this repo.** It only makes sense on a root-run, single-owner setup. |
| Test-only override for exercising the guard against a throw-away clone | **Not in this repo.** |
| Hook for "agent asks for credentials, must say where to put them" | Not in this repo. Detector only: `bin/secret-scan`. |
| "Cron does not commit code to main" | Not enforced by `scripts/daily-git-snapshot.sh`. Treat as open. |

### What the shipped wrapper does

- Walks PATH to find the real git (or `CCM_REAL_GIT`) and `exec`s it after the checks. Parses `-C`,
  `--git-dir`, `--work-tree` so the *target* repo is judged, not the cwd.
- **Judged by effect, not spelling.** Flags are normalised first (`-df` -> `-d -f`, `--delete` ->
  `-d`, `--force` -> `-f`), because a lock on the door with the window open is not a lock:
  `branch --delete --force`, `checkout -f`, `restore --worktree` all got around a block on the
  literal `-D` / `--hard`.
- Blocked in the shared repo: `reset --hard`, `branch -D` / `-d -f` / `-M`, `checkout -f` or
  `checkout -- paths`, `restore` of the worktree, `switch -f`, `clean -f`, `stash clear|drop`,
  `gc --prune`, `prune`, `reflog expire|delete`, `update-ref`, `tag -d`, `worktree remove -f`.
- `filter-repo` and `filter-branch` are blocked in worktrees too, because worktrees share the
  history. Other destructive verbs stay allowed in a worktree (it is the agent's own branch).
- `update-ref` has one exception: repairing a branch whose current target is not a readable commit,
  moving it to an intact one. Added after a cut-off write left a branch on an empty object and the
  repair procedure itself hit the block. On a healthy branch the same call stays blocked.
- Nested self-standing repos (a notes vault, a published showcase) are not the shared repo; they are
  judged by the repository git reports, not by the path prefix.
- Optional `CCM_GIT_GUARD_BLOCK_REMOTE=1`: for a repo whose history must never be published, block
  `remote add|set-url`, remote/`insteadOf` config and any push, so "there is no remote" is a
  construction rather than a coincidence. Off by default.
- Project repos under `<workspace>/Project-*/.git` get the same destructive protection. If a release
  queue keeps a state file for the project, direct moves of `master` (commit, merge, pull, rebase,
  reset, push/fetch into master) are blocked too; branches and reads are free. The queue itself
  merges with the real git. The releaser is `releaser.py`, **not in this repo**, so this half only
  activates if you provide a state file.
- If settings cannot be read it falls back to defaults with a warning, never a silent disarm.

## Lessons from deployment

1. **Worktrees must be inside the guarded set.** They share the main `.git`, so a root commit in a
   worktree writes root-owned objects into the shared store.
2. **Environment through sudo.** A plain `sudo -u owner git` drops `GIT_*` and `EDITOR`, which would
   break commit authorship. The redirect forwards them explicitly. Proven: `GIT_AUTHOR_NAME` arrives
   in `git var`.
3. **Do not test the guard against the live repo.** The tests use a throw-away clone.
4. **Absolute-path callers bypass it.** Anything calling `/usr/bin/git` directly skips both redirect
   and block (a build script did). The wrapper catches PATH calls, which is nearly everything; fix
   absolute calls when found. Likewise a cron job with its own PATH needs the guard directory added
   to that PATH line. The guard protects against accidents, not against an adversary, who has the
   real binary.
5. **Side benefit:** a root-run build that reported "no git" started seeing the repo, because git now
   ran as the owner.
6. **Installing a binary that shadows a system one is persistence, and the permission classifier was
   right to stop it three times.** It went in only after explicit human approval. The repo's
   installer is user-scope for that reason.

## A side decision: a dedicated git-owner agent

First answer, wrong: no dedicated agent, because an agent does not stand between a command and the
disk, a hook does. That attacked something nobody had asked for. The operator wanted an owner
*above* the mechanisms (designs the rules, reviews incidents, fixes things), the same relation the
archivist has to the swarm. And without an owner the domain stays ownerless, which is the exact cause
of the incident. Resulting split: the git agent designs, the infra developer agent implements, the
agent owning a public repo owns that repo's content, the release agent decides what ships, the
archivist owns the swarm and its docs.
