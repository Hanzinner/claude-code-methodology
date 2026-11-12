# shell

### `pkill -f` / `pgrep -f` matches your own shell
- **Symptom:** the command dies silently (exit 144/1, no output), or a wait loop `until ! pgrep -f X` hangs forever "seeing" a process that isn't there.
- **Why:** `-f` matches the full command line of ANY process — including the bash or ssh whose command line contains the pattern. The hunter becomes the target; over ssh, it kills its own session.
- **Right way:** kill your own process by PID (`PID=$!` → `kill "$PID"` in a `trap`; a PID file for long-running rigs). With no PID, put a character class in the pattern so it can't match itself: `pgrep -af '[q]emu-system'`. Remote commands (a line containing `ssh`) have the same problem.
- **Seen:** 8+ times across 6 agents — then mechanized as a gate.

### `pkill` by name kills other agents' processes
- **Symptom:** a parallel agent gets BrokenPipe or a dead VM in the middle of a run — it looks like a flake.
- **Why:** `pkill -9 qemu-system-x86` (even without `-f`) matches the process name — it kills same-named processes in ALL work trees on the machine. The damage lands on the neighbour, so the author of the command never gets feedback.
- **Right way:** kill only your own: by PID, or with a script that filters by your own tag. Recommending a kill command in a shared doc? First check "WHOSE processes will it kill".
- **Seen:** 2 times.

### `pkill` with no victims breaks the chain
- **Symptom:** after `pkill X` the rest of the `&&` chain, or of a script under `set -e`, never runs.
- **Why:** pkill returns 1 when nothing matched.
- **Right way:** `pkill ... || true` when "no target" is a normal state.
- **Seen:** once.

### `$(… | grep …)` under `set -euo pipefail` kills the script exactly in the normal state
- **Symptom:** a gate or hook silently dies when "everything is fine" (clean tree, no matches); a hook crashes outright.
- **Why:** grep with no match exits 1; `pipefail` lifts that to the whole pipeline, and `set -e` / `trap ERR` kills the script. `grep | head` adds SIGPIPE on top.
- **Right way:** a grep inside a substitution under pipefail always gets `|| true`. Check: `bash -c 'set -euo pipefail; d=$(printf "" | grep -v x | head -3); echo ok'` must not print `ok` — if it does not, the trap is there.
- **Seen:** 5+ times (a dirty-tree watcher killed a release runner for being clean; SIGPIPE crashed a watcher; a sweep found 3 more of the same).

### A destructive chain without `set -euo pipefail`
- **Symptom:** a destructive command ran in the wrong directory (`filter-repo` rewrote the main repo: 808 → 125 commits).
- **Why:** `clone` failed, `cd` failed, the chain carried on — and the destructive step ran in the current directory.
- **Right way:** a destructive chain only under `set -euo pipefail`, with a `pwd` check before the destructive step and a backup of the target BEFORE the operation.
- **Seen:** once, expensive.

### Silent death under `set -e` — the log is empty
- **Symptom:** a cron script "doesn't work" and its log says nothing; or it redoes the same work every tick.
- **Why:** `set -e` exits on the first non-zero code without a word — before your `log` line ever runs (e.g. `git commit` → "nothing to commit" when the sha is already merged).
- **Right way:** `trap 'echo "ABORT: line $LINENO: $BASH_COMMAND" >>"$LOG"' ERR`; check up front for steps that may legitimately be a no-op (`git merge-base --is-ancestor` → NO-OP, remove the marker).
- **Seen:** repeatedly; one case left a snapshot cron silently dead for 2 hours.

### A non-critical step after the point of no return kills the report
- **Symptom:** the main thing (tag, deploy) is done, but notifications and reports haven't arrived for weeks.
- **Why:** under `set -e`, a failing non-critical step (a broken grep pattern) aborts the script after the important part is already finished.
- **Right way:** non-critical steps after the point of no return get `|| true` plus a WARN line in the log.
- **Seen:** once.

### A block appended to the end of a script lands after `exit 0`
- **Symptom:** the feature is "installed" but has never fired once (2 weeks of dead code).
- **Why:** the block was appended to a file that ends in `exit` / `return`.
- **Right way:** read the tail of the file before appending; test a feature with a rare trigger by faking the trigger on the day you install it.
- **Seen:** once.

### Editing a bash script while it is running
- **Symptom:** a script under cron runs a truncated or mixed command; or a long run breaks with `unexpected EOF` on the last line after you edited the file mid-run.
- **Why:** bash reads a script piecemeal by byte offset; changing the file length mid-execution shifts the position.
- **Right way:** before editing, `pgrep -af '[n]ame.sh'`; if it runs, wait, or write a new file and `mv` it over (atomic inode swap — the running process finishes on the old one). Or make it immune: wrap the whole body after `set -euo pipefail` in `{ … }` — bash parses the block completely before executing it.
- **Seen:** 3 times (twice in one evening on a test script).

### A file created by a Write tool has no `+x`
- **Symptom:** a script registered as a direct call (hook, cron) gets `Permission denied` — and under a fail-open wrapper that's silent, for weeks.
- **Why:** editor/Write tools create `rw-r--r--`; your manual test `python3 script` works without `+x`, so it never catches it.
- **Right way:** `chmod +x` right after creating it; accept it with the same invocation production uses.
- **Seen:** one hook stayed dead for 33 days.
- **Variant — atomic replacement of a live file:** a `.new` written by Python (`open(p+'.new','w')`) or a Write tool is 644, and `mv X.new X` carries the `.new` mode over — a live hook without `+x` is a dead hook (a watcher caught one in 13 minutes). Replace through a small `swap-live X.new` helper: syntax check → copy mode and owner from the live file → `mv` → verify `+x`.

### Children under `flock` inherit the lock fd
- **Symptom:** later runs quietly exit on `flock -n` for hours — "cron doesn't work".
- **Why:** children and grandchildren started under the lock inherit the lock file's fd and keep the lock after their parent dies (orphans).
- **Right way:** start children under flock with the lock fds closed: `cmd 9>&- 8>&-`; long-lived clients get a `timeout`.
- **Seen:** 3 times (CI stood for 2 hours; a hung tmux client held a lock).

### A fixed pause racing an event of variable length
- **Symptom:** a "flake": occasional FAIL on a healthy system, truncated logs, the first bytes of a command eaten.
- **Why:** `sleep X` was tuned on one example; a change in scale (file size, load, cold start) makes the event longer than the pause. It's a race by construction.
- **Right way:** measure the event first; then wait for the EVENT with a deadline (a log marker, an echo, "saved"), derive the deadline from the size; a timeout is a real FAIL with the log tail, not a verdict.
- **Seen:** 6+ times (one instrument slept 1.2 s against an event of 0.44–1.98 s).

### A long command with no output looks like a hang
- **Symptom:** the human interrupts a "hung" command and the work is lost.
- **Why:** a multi-minute silent block (`apt-get install -qq …`) is indistinguishable from a freeze.
- **Right way:** short steps with visible output; long work goes to the background with a bounded wait and a state check.
- **Seen:** 2 times.

### `cd` persists between calls; relative paths
- **Symptom:** a script "ran" but the artifact is stale (it ran from the wrong directory); a hook decides you are a different agent.
- **Why:** the working directory survives between Bash calls; scripts with relative paths depend on it; a hook that injects context by looking for a file in the cwd now sees another agent's folder.
- **Right way:** always absolute paths; never `cd` into another agent's folder.
- **Seen:** 2 times.

### `2>/dev/null` swallows `fatal:`
- **Symptom:** the command "passed" and there is no result.
- **Why:** the only error signal went to stderr, which was muted.
- **Right way:** don't mute stderr on critical steps (git, anything destructive); filter the output instead of throwing it away.
- **Seen:** once.

### Text with an apostrophe inside single quotes
- **Symptom:** a truncated duplicate of the message landed in the file.
- **Why:** an apostrophe (or a typographic one) inside a `'…'` argument ends the quoted string early.
- **Right way:** pass free-form text through a quoted heredoc `<<'EOF'` or a file, never as a single-quoted argument.
- **Seen:** once (an inbox poster script).

### `awk -v var="$text"` interprets escape sequences
- **Symptom:** text written through awk differs from the input (`\b` → backspace `^H`, `\t` → tab, `\\` → `\`); a "did my text land?" check can't find its own line.
- **Why:** awk treats the value of `-v` as a string literal with escapes. Regexes in the text (`\b`, `\s`, `\d`) are typical content of agent messages.
- **Right way:** pass free-form text through the environment: `ENTRY="$text" awk '{… print ENVIRON["ENTRY"] …}'`. Use `-v` only for your own constants without `\`.
- **Seen:** once — it produced 10 duplicate messages through a repair → pending → watcher loop.

### Stopping a background process "by pattern in the command" hits bash wrappers
- **Symptom:** you meant to kill only `python …script.py`, and the `bash -c …` wrapper died too (background task "failed 144") along with your own shell.
- **Why:** `pgrep -f` + `case "$cmd" in *".venv/bin/python "*` — the wrapper's command text `bash -c "… .venv/bin/python script.py …"` contains that string as well.
- **Right way:** use the PID saved at launch (`$!`), or check the NAME OF THE EXECUTABLE, not the whole line: `[ "$(ps -o comm= -p $p)" = python ]`.
- **Seen:** once.

### A `pgrep` character class doesn't help when the name is elsewhere in your own command line
- **Symptom:** a background chain `until ! pgrep -f '[c]heck_stream.sh'; …; ./deploy/check_stream.sh 75` hangs — second time in a day.
- **Why:** the class saves the pattern from matching itself, but NOT from the plain text `check_stream.sh` further along the same command line — pgrep finds your own bash.
- **Right way:** wait for a process by PID (`while kill -0 $PID`) or by a result marker file, not by name, whenever that name appears in your own line. Cost: a rollout didn't start, ~6 min.
- **Seen:** 2 times.

### `cut -c` breaks Cyrillic (any multi-byte text) → `grep` silently "doesn't see" the file
- **Symptom:** `grep` over a log finds nothing; even `grep -c ""` prints no number (not 0 — nothing); `grep -v … > file` leaves the file EMPTY. Python on the same file: `UnicodeDecodeError`.
- **Why:** two layers. (1) GNU `cut -c1-N` and `head -c` count BYTES — a two-byte letter is cut in half → invalid UTF-8. (2) `grep` in the agent's shell can be a harness function that calls ugrep with `-I` (check `type grep`): a file with invalid bytes counts as binary and is silently SKIPPED.
- **Right way:** truncating text for a log: `cut -c1-100 | iconv -f utf-8 -t utf-8 -c` (or by characters in Python). Filtering or cleaning a log that may contain junk: `command grep` (the real GNU one) or Python in byte mode (`open(p,'rb')`). **Before overwriting a file with a filter's result — back it up and compare line counts.**
- **Seen:** once — a log was zeroed by a filter; a backup saved it.

### A script for cron or a watcher must be tested in cron's environment, not in your shell
- **Symptom:** a watcher's two checks cried false alarms for 17 hours; the script works by hand.
- **Why:** cron gives `PATH=/usr/bin:/bin` — without `/usr/sbin`. `runuser`, `ip`, `ss`, `iptables` are "not found" (rc=127), while an interactive root shell and even `env -i bash` (bash supplies its own default PATH) find them.
- **Right way:** test with `env -i PATH=/usr/bin:/bin HOME=/root /bin/bash -c '/path/to/script'`. Fix: `export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` as the first line after the shebang.
- **Seen:** once.

### `sed -i` on a symlink turns it into a regular file
- **Symptom:** an nginx config edited through `sites-enabled/<name>` (a symlink to `sites-available/<name>`) — for 12 hours nginx read a copy, and other agents' edits to `sites-available` had no effect (a new server block "didn't exist").
- **Why:** GNU sed writes the result as a NEW file instead of following the link.
- **Right way:** edit only the target (`sites-available`), or `sed -i --follow-symlinks`. A watcher should check that the entry is still a link.
- **Seen:** once.

### Cron has no locale, and `runuser -u` keeps the wrong `HOME`: a script "breaks" only under cron
- **Symptom:** a script works in the terminal and fails (or behaves differently) from cron, `env -i`, or systemd — with PATH and permissions correct. A publication gate failed its entire self-check matrix under `env -i`, including the clean-tree case.
- **Why:** cron sets no `LANG` → `C`/`POSIX`, and non-ASCII is processed byte by byte: `grep -P '\p{L}'`, `[[:alpha:]]`, sorting and string comparison with non-ASCII markers all change meaning; the "letter" class doesn't match Cyrillic. And `runuser -u <user>` leaves `HOME=/root`.
- **Right way:** the locale is part of the TOOL, not of the environment: `export LC_ALL=C.UTF-8` (and `LANG`) in the first lines of any text-processing script, before the first text operation; don't rely on a wrapper that "sets LANG" — the next caller won't. Under another user: `runuser -u <user> -- env HOME=/home/<user> …` (or `runuser -l`). Prove the fix the way cron runs it: `env -i PATH=/usr/bin:/bin HOME=/root bash script.sh`.
- **Also:** a regression test for this must FAIL on the version without the fix. A "clean" fixture can pass even with a broken locale — then the test is decoration, and the real check belongs where the condition actually occurs (the nightly cron run).
- **Seen:** 2 times.

### A test root variable isolates files, but not side-effect calls made by absolute path
- **Symptom:** a script test with `ROOT=$(mktemp -d)` cleans up after itself, yet entries appear in the live inbox/log.
- **Why:** the root variable only moves paths that the script builds from it; the mailer, logger and notifier are called by their own absolute paths. A separate override variable per such call doesn't help — it gets skipped, and a run against an old version doesn't know it.
- **Right way:** test mode is switched on by ONE root and itself redirects every side effect inside it (a registration script: with `REGISTER_AGENTS_ROOT` set, the report goes to that root's inbox). In the test, md5 the live files before and after.
- **Seen:** once — 5 reports landed in a live inbox.

### `| head -1` / `| grep -q` under `set -o pipefail` — a "failure" of a successful command
- **Symptom:** the script returns rc 141 after doing everything (mail delivered, service "failed"); or a function "doesn't find" a line that is there — and the script does extra work (a duplicate).
- **Why:** the right end of the pipeline exits early (head read its line, `grep -q` found a match) → the left end writes into a closed pipe → SIGPIPE → pipefail takes the left end's rc. On small input the left end manages to finish into the 64 KB buffer, so tests are green.
- **Right way:** first line: `${text%%$'\n'*}`; search with a single process (`awk '…index($0,ENVIRON["X"]){f=1} END{exit !f}'`, or `grep -qF … file` without a pipe). Test with input >64 KB.
- **Seen:** 2 scripts.

### A tool's disposable cache "cleaned" by moving it to a trash folder — the disk grows without bound
- **Symptom:** a VM disk grew by tens of gigabytes in a day; the trash folder holds thousands of identical directories (headless-Chrome profiles of ~35 MB each).
- **Why:** a check script made `mktemp -d` for a browser profile on every run and ended with `mv` into the trash ("deletion = mv, not rm"). Nobody empties the trash, and there were thousands of runs.
- **Right way:** what the tool itself created as temporary, the tool itself deletes: bash — `trap 'rm -rf -- "$tmp"' EXIT` after checking that the path is under your own prefix; Python — `shutil.rmtree(tmp, ignore_errors=True)` in `finally`. The "move to trash" rule is for files that existed before you. After a series of runs: `df -h /` and `du -sh` of the trash before and after.
- **Seen:** once.

### `builder | tail -1 && cp …` copies the broken output
- **Symptom:** a broken page was shipped to a person.
- **Why:** the pipeline's exit code comes from its last command (`tail`), so the `&&` after it can't see the builder fail.
- **Right way:** `set -o pipefail`; or have the builder remove (rename) its result on failure, so there is nothing to copy.
- **Seen:** once.

### `echo "… $(cmd) rc=$?"` — `$?` is already from `$(cmd)`, not from the previous command
- **Symptom:** a cycle log writes `rc=0` for a run that failed — a false green.
- **Why:** the `$(date …)` substitution in the same line runs before `$?` is expanded and overwrites it.
- **Right way:** `cmd; rc=$?` as a separate command right after `cmd`, then `echo "$(date) rc=$rc"`; and log the run's own summary line (no summary = not a result).
- **Seen:** once.

### `docker exec` without `-i` silently swallows a heredoc
- **Symptom:** `docker exec <c> psql … <<SQL … SQL` — rc=0, psql even prints something, but none of the heredoc's commands ran (roles/databases not created).
- **Why:** without `-i` the container gets no stdin; psql sees empty input — that is not an error.
- **Right way:** `docker exec -i …` for any stdin input; afterwards verify the result with a query (`select … from pg_roles`), not with rc.
- **Seen:** once.

### `head -c N` / `cut -c` / awk `substr` cut by BYTES — the preview ends mid-letter
- **Symptom:** in another agent's inbox a message ends in a half character (a lone `\xd0` byte); a Python tool (`encoding="utf-8"`) crashed on it, and the script silently put an empty file over the inbox.
- **Why:** a watcher made a preview with `head -c 200`; Cyrillic is 2 bytes per letter, the cut fell mid-character, and an agent copied the preview into a message.
- **Right way:** every truncation goes through `| iconv -f utf-8 -t utf-8 -c` (drops the incomplete character; add `|| true` under `set -e`); a reader of someone else's text uses `errors="surrogateescape"`, so a bad byte comes back unchanged instead of crashing.
- **Seen:** once (see also the `cut -c` lesson above).

### `bash -c "one command"` does exec — no parent process is left in the tree
- **Symptom:** a "two tabs" test substituted a fake `claude` process (`cp /bin/bash claude; ./claude -c "bash x.sh"`), and the script still saw the real session as its ancestor.
- **Why:** bash given a single simple command replaces itself with it (exec), and the fake "claude" vanishes from the ppid chain.
- **Right way:** in a test use `-c "cmd; true"` (the second command disables exec); in code that finds an ancestor by `comm`, remember that intermediate shells may be absent.
- **Seen:** once.

### `sed s/…/&/` with `&` in the replacement inserts the whole match, not the character "&"
- **Symptom:** editing a line with a JS expression `a || b` via `sed -i "s/X/&/"` left `... || &` and broke a Python file; noticed 5 hours later at `py_compile`.
- **Why:** in a sed replacement `&` means "the matched text".
- **Right way:** edits that contain code go through a Python script with `assert old in s`, followed by `py_compile`.
- **Seen:** once.

### A shared lock file for root and another user: `/run` and `/var/tmp` are both traps
- **Symptom:** a flock wrapper run by a normal user instantly fails with "lock not released" (though nobody held it); or root gets `Permission denied` on a 666 file in `/var/tmp`.
- **Why:** in `/run` a root-created file is 644 — the other user can't open it for writing. In `/var/tmp` (sticky bit, `fs.protected_regular=2`) root can NOT open with `O_CREAT` (`>>`, `>`) a file owned by someone else, even at 666. And `exec 9>>lock` without checking the return code = flock on a non-existent fd → "failed" with the wrong message.
- **Right way:** a dedicated directory `0777` WITHOUT sticky (e.g. `/var/tmp/<project>-locks/`), files 666; `exec 9>>"$LOCK" || { echo "could not open lock"; exit 1; }` with its own text, distinct from "busy". Test: both users in turn and simultaneously (the second must wait).
- **Seen:** once.

### `cmd | tail` / `cmd | grep` hides a failure: `set -e` doesn't stop the chain
- **Symptom:** in a chain "tests → commit → mail a colleague", the tests failed, the commit went through, and the mail with the sha went out. Twice in one day.
- **Why:** without `pipefail` a pipeline's code is the code of its last command (`tail`, `grep`, `cut`), which succeeds; and `;` between steps ignores the previous error anyway.
- **Right way:** `set -e; set -o pipefail` at the start of such a command; take the sha for the mail after checking `[ "$S" != "$OLD" ]`; send the mail as a separate step after reading the commit's output.
- **Seen:** 2 times in a day.
