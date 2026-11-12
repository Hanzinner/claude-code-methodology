# git

### `git add a b c`: one bad path, nothing added
- **Symptom:** a commit titled "add new file" that doesn't contain the file.
- **Why:** `git add` with several paths fails atomically (`fatal: pathspec … did not match`); `2>/dev/null` swallowed the fatal. The files were in the main checkout, the commit was made from a worktree.
- **Right way:** never silence git's stderr. After the commit run `git show --stat` and read the file NAMES. Know which tree you are in (`git rev-parse --show-toplevel`). To fix: amend only your own unpushed commit; on a shared master, a second commit.
- **Seen:** once.

### `git add -A` takes other people's changes and resurrects a staged `git rm`
- **Symptom:** a commit "remove X" committed X (`M` instead of `D`).
- **Why:** `git rm` is only index state. While you worked, another agent recreated the file and `add -A` overwrote the deletion. `git status` showed `M` — it was printed and not read.
- **Right way:** `git add -u` plus explicit paths. Before the commit, `git status --porcelain` and check the EXPECTED LETTERS (wanted `D` → must be `D`). A file that must not be in git goes into `.gitignore` plus `git rm --cached`.
- **Seen:** once.

### `git commit` takes the WHOLE index — shared working tree
- **Symptom:** your commit about a document swallowed someone else's release; the snapshot cron picked up another agent's unfinished WIP and it shipped inside a third party's release.
- **Why:** `add` puts into the index, `commit` takes the whole index, including what another writer staged (a runner doing `merge --no-commit`, another agent). An exception in your `add` doesn't help when you weren't the one who staged.
- **Right way:** every agent works in its own worktree on its own branch; commit nothing in the master tree (not even docs). Automation merges in its own worktree and only fast-forwards master. The snapshot cron skips a tick while `MERGE_HEAD` exists.
- **Seen:** 3 times.

### A commit made as root makes `.git` root-owned — the cron under the repo owner dies silently
- **Symptom:** the snapshot cron silently doesn't commit for days; `dubious ownership` / `Permission denied` on `refs/logs`.
- **Why:** the repo belongs to a regular user, agents run as root; `sudo git commit` or any root git creates root-owned objects. A command run with cwd OUTSIDE the repo (e.g. `git clone <path-to-repo> …`) bypasses the git wrapper that would have switched the user.
- **Right way:** plain `git` (a wrapper earlier in `PATH` switches to the owner inside the repo's territory); never `/usr/bin/git` directly. Outside the territory, explicitly `sudo -u <owner> git …`.
- **Seen:** 3 times (one case: 4 days of silent failure).

### Destructive git in the main repo
- **Symptom:** history rewritten (808 → 125 commits).
- **Why:** `filter-repo` ran in the wrong repo (a command chain without `set -e`, see [shell.md](shell.md)).
- **Right way:** destructive operations (`filter-repo`, `reset --hard`, `branch -D`, `push --force`, `clean -f`, `gc --prune`) only in a throwaway clone OUTSIDE the main repo; back up `.git` BEFORE the operation (that backup is what saved it). In the main repo a wrapper blocks them (exit 88).
- **Seen:** once.

### `reset --hard` in a shared tree destroys other agents' uncommitted files
- **Symptom:** (near-miss) "cleaning up after myself" almost wiped another agent's work.
- **Why:** a shared tree holds other agents' uncommitted files; `reset --hard` doesn't distinguish "mine" from "theirs".
- **Right way:** in a shared tree neither reset nor stash what isn't yours. Someone else's file blocks your merge → message the owner with the exact list. A destructive operation done for process tidiness is worse than the problem.
- **Seen:** 2 times (the permission classifier stopped one).

### Tracked build artifacts and crash files block merge/release
- **Symptom:** `git merge master` → "would be overwritten"; the release gate stands because of a "dirty tree" though nobody edited anything.
- **Why:** `target/`, `.iso`, `__pycache__` are tracked and get dirty with every build. A compiler crash leaves `rustc-ice-*.txt` in the tree — the symptom ("dirty tree") and the cause (overload) look unrelated.
- **Right way:** artifacts → `git rm -r --cached` plus `.gitignore`. "Gate says dirty" → `git status --porcelain` and look for fresh uncommitted files, crash artifacts included (move them to the trash dir, add the pattern to `.gitignore`).
- **Seen:** 3 times.

### Phantom submodule
- **Symptom:** in fresh trees/CI, `No such file` for the content of a directory that "is in the repo".
- **Why:** a gitlink without `.gitmodules` — git stores only the pointer, the content never arrives.
- **Right way:** either a real submodule with `.gitmodules`, or commit the files as regular files.
- **Seen:** once.

### The working tree "forgot" changes after a commit
- **Symptom:** the code is in HEAD, but the disk holds the old version (a staged revert of your own work).
- **Why:** not established (no branch operations in the reflog — files were rewritten from outside).
- **Right way:** first `git log` / `git diff HEAD --numstat`; do NOT redo from scratch — the work may be intact in the commit. Commit early and often: that is what saved it.
- **Seen:** once.

### Duplicate feature: master not checked before starting or releasing
- **Symptom:** the release runner fails on a conflict and sends the same FAIL every cycle; your commit duplicates something already merged.
- **Why:** two agents took the same feedback into their queues; before releasing, only their own branch was compared.
- **Right way:** before starting a feature and before a release marker, `git log master..<branch> --oneline` (what exactly am I shipping) plus `git grep <key symbols>` on master (is it already done).
- **Seen:** 2 times.

### A secret in a repo under an auto-commit cron
- **Symptom:** a token was committed ~2 minutes after appearing in an agent's folder; history had to be rewritten.
- **Why:** a snapshot cron commits the whole repo every ~10 minutes.
- **Right way:** credentials live only in a config directory outside the repo (e.g. `~/.config/<project>/`). An agent that asks for credentials says itself where to put them.
- **Seen:** once.

### A root-owned 0600 file kills `git add -A` for the cron user — silently under `set -e`
- **Symptom:** the snapshot cron produces no snapshots for 2 hours; it looks like "cron is dead" — but cron ran every 10 minutes (check `journalctl | grep "(<user>) CMD"` before treating cron).
- **Why:** a service/agent running as root with umask 077 left a `root:root 0600` image inside the tree → `git add -A` in the cron user → `Permission denied` → `set -e` exited WITHOUT a log line.
- **Right way:** `git add -A --ignore-errors` plus a WARN in the log; `trap ERR` that writes a line; a watchdog on the snapshot's freshness. Wider lesson: a script under `set -e` without `trap ERR` — its log lies by silence.
- **Seen:** once.

### "Verified from a fresh clone" passed — but there was no clone
- **Symptom:** `git clone <url> $DIR && cd $DIR && ./install.sh …` reports "9/9 ok", but it tested the LOCAL copy: the clone failed with `could not create leading directories … Permission denied`, the `cd` was skipped, the next commands ran from the previous directory.
- **Why:** a git wrapper sees cwd inside the repo → `exec sudo -u <owner> git`; the owner can't write into root's scratch dir → clone fails. `&&` stops only its own chain; the rest of the script (a separate line) runs from wherever the shell stood.
- **Right way:** clone for verification from `cd /` (outside the repo) or with `/usr/bin/git clone`; every step with `|| exit 1`. In the proof print the clone's `git log -1` and `pwd`, and confirm the tested files come from the clone (compare one file with what got installed).
- **Seen:** once (caught immediately: the HEAD line was missing).

### `.gitignore`: a comment on the same line as the pattern kills the pattern
- **Symptom:** `models/hub/   # CLIP weights…` in `.gitignore`, but `git check-ignore -v` says nothing; 578 MB of weights stay candidates for the auto-commit.
- **Why:** in `.gitignore` a comment is only a line that STARTS with `#`; everything after the pattern (spaces, `#…`) becomes part of the pattern.
- **Right way:** comment on its own line above the pattern. After the edit, `git check-ignore -v <path>` must name the `.gitignore` line. Model caches (HF_HOME, torch hub) go into ignore before the first download: the cron commits within minutes (here it managed to commit a 191-byte `.incomplete`).
- **Seen:** once.

### Interrupted write → 0-byte object → `fatal: bad object HEAD` (and repair without losing work)
- **Symptom:** `git log` / `git status` fail with `fatal: bad object HEAD` or `error: object file … is empty`. The auto-commit cron fails every time; working files are intact.
- **Why:** the process was cut mid-`git commit` (VM halted, disk didn't flush, power loss): object files created, content not written. Git isn't broken — it holds an unfinished file and rightly refuses to trust it. Worst case: the commit the branch points to is the empty one, so the whole branch is unreadable though all earlier history is fine.
- **Right way (worked 2026-09):**
  1. `tar -cf <outside-repo>/git-backup.tar .git` — FIRST, before anything. The repair can also go wrong.
  2. Find the broken ones: `find .git/objects -type f -size 0`. They can't be recovered — the content exists nowhere, and a backup doesn't help: the object WAS zero when taken. You lost the metadata of those commits, not the files.
  3. Move the empty objects to the trash dir (don't `rm`; don't wait for "git will fix itself").
  4. Find the last intact commit: `git cat-file -t <sha>` → `commit`. Take it from another worktree/branch `git log`, or `.git/logs/HEAD` if the reflog is alive.
  5. `git update-ref refs/heads/<branch> <intact-sha>` — move the branch back. NOT `reset --hard` (in a shared tree it destroys others' uncommitted files, see above).
  6. Don't forget the index: `git fsck` after step 5 still complains `invalid sha1 pointer in cache-tree of .git/index`. `git read-tree HEAD` fixes it (leaves files on disk alone, rebuilds the index; staged state is lost — acceptable).
  7. Work after the broken commit is NOT lost: files on disk are intact, the next commit picks them up.
- **What remains:** reflog entries pointing at the dead sha — `git fsck` complains forever. It's a local journal, not history. `git reflog expire --expire-unreachable=now --all` cures it, but a permission classifier may block it as destructive, so the complaints can stay.
- **Prevent (after the SECOND such incident, 2026-10):** `git config core.fsync all` and `core.fsyncMethod fsync` — git flushes objects to disk before updating the ref, so a cut mid-commit no longer leaves a ref on an empty object. Cost on snapshots: 0.7 s. Set it in EVERY repo under an auto-commit at creation, not after the first accident.
- **Main point:** an empty object = lost metadata, not lost code. Panic costs more than the damage; the urge to "re-clone / cut the history" costs more than the defect.
- **Seen:** 2 times.

### A "main repo" gate keyed on path prefix catches nested standalone repos
- **Symptom:** a block on push/remote/destructive operations in "the main repo" suddenly breaks the sync of a notes vault or the publication of a public showcase that live INSIDE its directory.
- **Why:** `[[ $PWD == <main>/* ]]` can't tell the main repo's working tree from nested repos with their own `.git` and remote.
- **Right way:** identify the repo by the storage git itself names: `git -c safe.directory='*' rev-parse --path-format=absolute --git-common-dir` == `<main>/.git` (worktrees share the storage with the main repo — they are "main" too). Test the gate on a nested repo as well.
- **Seen:** once (caught by the author's own live check within minutes).

### "repository is potentially unsafe / owned by someone other than the current user" (editor warning)
- **Symptom:** the editor shows a red "The git repository in the current folder is potentially unsafe as the folder is owned by someone other than the current user" with a *Manage Unsafe Repositories* button. In the terminal `git` may work fine.
- **Why:** sessions and the editor run as root, the working tree belongs to another user (on purpose: the wrapper keeps ownership with that user). Since git 2.35.2 it refuses to work in a repo owned by someone else unless the path is in `safe.directory`. The main repo is often already trusted — the warning comes for OTHER ones: worktrees and nested repos (a vault, a showcase, a docs corpus). The editor scans subfolders and finds them all.
- **Right way:** add each path to the trusted list for the user the editor runs as: `git config --global --add safe.directory <path>` (or the button, same thing). To find where it hurts, walk all `.git` and see where `git -C <repo> status` fails. **Names with spaces:** iterate with `find -print0` + `read -d ''`, or the loop splits the path and you "fix" a nonexistent repo. `safe.directory` weakens nothing in the wrapper's protection (checked right after: `branch -D` in the main repo still exits 88).
- **Don't add when** the path is really foreign (a clone with someone's hooks): the check exists precisely against hooks that run in your name.
- **Seen:** once.

### Cache and generated files under git: treat the CLASS, not the instance
- **Symptom:** someone asks to remove `__pycache__` from one directory from tracking. You do — a week later the same request for another directory.
- **Why:** `.gitignore` is written per project, when it hurts, so a global rule never appears. A check: the root had NO rule for `*.pyc`, and 34 such files were tracked across four projects — each got there via an auto-snapshot.
- **Right way:** a request for one directory → count the class across the repo: `git ls-files | grep -c "__pycache__\|\.pyc$"`. More than one place → a rule in the ROOT `.gitignore`, not the project's. Same for `.pytest_cache/`, `.mypy_cache/`, `node_modules/`, `target/`, `dist/`, `*.log`. `.gitignore` doesn't affect already tracked files — `git rm --cached` is needed (files on disk stay). Proof per class: `git check-ignore -v <new file>` must show the rule's line; one check "for everything" proves nothing.
- **Seen:** 2 times.

### Non-ASCII in a path: git escapes it to octal — any pipe over git output lies
- **Symptom:** a script parsing git output (`diff --cached`, `status`, `ls-files`, `ls-tree`) suddenly fails or "doesn't see" files — only those with non-ASCII characters in the PATH. Under `set -euo pipefail` that kills the script on every run.
- **Why:** by default `core.quotepath=true`: git prints such a path quoted with octal escapes — `docs/café/x.jsonl` → `"b/docs/caf\303\251/x.jsonl"`. `grep` on UTF-8 then gives 0 matches (false negative), and `reset -- "$f"` / `sha1sum -- "$f"` receive a path that doesn't exist.
- **Right way:** `git -c core.quotepath=off …` in EVERY command whose output you parse (don't rely on global config — the next caller will differ). Bonus: with `off` the prefix escaping goes too, so the path works for `reset`/`sha1sum`/`test -e` as is. More robust than any text parsing: `-z` (`git diff --cached -z --name-only`) + `read -d ''`. Proof that the fix is live: make a file with non-ASCII in the PATH (not just the name) in a sandbox and run your pipe. An ASCII-path fixture never catches this class.
- **Seen:** 2 times (cost: an auto-snapshot failed on every run for an hour, nothing was committed; earlier, a false "files not in git" nearly caused a needless deletion).

### `git --git-dir … --work-tree=…` without `-C`: `ls-files` prints paths relative to cwd
- **Symptom:** a script under cron (cwd=/root) silently removed 80 files from the index; by hand, from another directory, all fine.
- **Why:** with cwd inside the working tree, `git ls-files` shows only the cwd subtree with paths relative to it; the code joined them with the tree root → "file missing" → `rm --cached`.
- **Right way:** `git -C "$WT" --git-dir=… --work-tree="$WT"` on EVERY call; a postcondition "the index holds as many as I added"; run the test with cron's cwd (inside the tree).
- **Seen:** once.

### `git commit -- <path>` doesn't take a `git rm --cached` of the same path
- **Symptom:** `git rm -r --cached X && git commit -- X` → "no changes added to commit", though `git ls-files X` is already empty.
- **Why:** a commit with paths means `--only`: git takes the path's state from the WORKING TREE. The files stayed on disk — to it, "nothing changed".
- **Right way:** check that the index holds only your changes (`git diff --cached --name-only | grep -v '^X/'` → empty) and run `git commit` without paths. In a shared tree only after that check (commit takes the whole index).
- **Seen:** once.

### A message in a tracked inbox containing a "sample secret" drops the recipient's inbox from snapshots
- **Symptom:** you asked for a scanner fix and pasted example lines (real forms and false positives) into the message → the secret scan flagged the recipient's inbox → the snapshot stopped committing it.
- **Why:** the scanner reads tracked files; a literal example is indistinguishable from a leak.
- **Right way:** in messages and docs that live in the repo write the shape (`PASSWORD="<16 letters/digits>"`) or a `file:line` reference, not a literal. Build test fixtures from fragments in code, not as a literal.
- **Seen:** once.

### Pathspec `'Project-*/'` with a trailing slash matches no files
- **Symptom:** a gate "new databases under Project-*" on `git diff --cached --name-only -- 'Project-*/'` returned empty — a database would have passed into the commit (the test showed it).
- **Why:** a pattern ending in `/` matches the directory itself, not files inside it (unlike `Project-X/` without a wildcard).
- **Right way:** `':(glob)Project-*/**'`. Always test with a file that MUST be caught — an empty result looks like "clean".
- **Seen:** once.

### A nested repo under root: "dubious ownership", and the wrapper's protection doesn't apply
- **Symptom:** a freshly split-out `Project-X/.git`: git refuses; after `safe.directory` root commits itself, `.git/index` becomes root-owned, `reset --hard` goes through.
- **Why:** the directory belongs to root, `.git` to the repo owner; the wrapper treats a nested storage as not-main and doesn't protect it.
- **Right way:** `git config --system --add safe.directory <path>`, ACL on `.git`; do the split through a script, not by hand. `git clone` of a local repo owned by someone else, from root: `--upload-pack "git -c safe.directory=* upload-pack"` (`GIT_CONFIG_*` doesn't reach it).
- **Seen:** once.

### A `data/` pattern in `.gitignore` silently catches `app/data/` — the file doesn't reach the commit
- **Symptom:** `git add app/data/x.txt` in a list with other paths → "paths are ignored", the rest is added, the commit passes without the file; at release the code fails without its data.
- **Why:** `data/` without a leading `/` ignores a directory of that name at any depth.
- **Right way:** before committing a new file, `git check-ignore -v <path>`; put code data into a uniquely named directory (`app/taxonomy/`), not `git add -f`.
- **Seen:** once.

### `git config user.name` in a worktree writes to the SHARED `.git/config` — the author changes for every agent of the project
- **Symptom:** in own worktree `git config user.name <agent>`, believing it is a setting of that copy. Worktrees share one `.git/config` (without `extensions.worktreeConfig`), so the lead and the DB agent would have committed under that name from then on. Noticed within a minute and removed (`git config --remove-section user`); no commits in that window.
- **Why:** `git config` without `--worktree` writes to the common config.
- **Right way:** set the author per commit: `git -c user.name=<agent> -c user.email=<agent>@example.invalid commit …`. The other path — `extensions.worktreeConfig true` plus `git config --worktree user.name …` — changes the repo format for everyone, so only by the repo owner's decision.
- **Seen:** once.

### `core.autocrlf=true` plus an editor that writes LF → "modified" files with an empty diff block pull
- **Symptom:** `git status` = `M`, `git diff` empty, `git pull` fails with "local changes would be overwritten".
- **Why:** a Windows clone with `autocrlf=true` (the Git for Windows default) checks out CRLF; a markdown editor re-saves LF.
- **Right way:** fix it in the repo, not on every machine: `.gitattributes` → `*.md text eol=lf`. One-off: `git checkout -- <files>` and pull. Diagnose with `git ls-files --eol <file>` (shows i/lf w/crlf and the attribute).
- **Seen:** once.
