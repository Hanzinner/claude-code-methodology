# hooks

### A defensive hook that fails open: missing dependency → everything allowed
- **Symptom:** the guard is "installed" and lets anything through.
- **Why:** it parsed its input with a tool that wasn't on the machine → crashed on every call → `exit 0` → ALLOWED. In defensive code an error silently becomes permission.
- **Right way:** blocking gates fail CLOSED; before registering one, feed it broken input — remove the dependency, send garbage, cut it off — and check it doesn't wave everything through.
- **Seen:** once.

### A substring match is not a command position
- **Symptom:** a hint or gate keyed on `ssh`/`git` in a Bash command blocks or fires on a *conversation about* the action, not the action: an inbox message about a ban, documentation with command examples, a heredoc that merely mentions those words.
- **Why:** the keyword is searched anywhere in the line; the command string contains the heredoc body; in `bash -c "text"` the text IS the command, so in general a parser can't tell a description from a call.
- **Right way:** detect by command position within a segment, recursing into wrappers; treat quoted heredocs (`<<'EOF'`) as data; strip heredoc bodies and quoted strings before matching, or accept it as noise and rate-limit it (dedup per hour). Write documentation with examples of the forbidden thing using the Write tool (a Bash hook doesn't see it).
- **Seen:** 2 times (heredoc case still open at the time).

### `return` instead of `break` in segment parsing; bypass through a wrapper
- **Symptom:** a harmless command earlier in the chain opens the door to a forbidden one; `runuser -l <user> -c '…'` slips past.
- **Why:** the verdict was made on the first segment; the target inside the wrapper's quotes wasn't parsed. The bug sat in inline python inside bash — unreadable, and the stray `return` was invisible.
- **Right way:** evaluate ALL segments; recurse into `bash -c` / `runuser -c` / `sudo`; keep a gate's logic in a separate `.py`, not inline. Mandatory tests BEFORE registering: (a) broken input, (b) bypass through a wrapper, (c) a conversation ABOUT the rule.
- **Seen:** 3 generations of one hook (17/17 after the fix).

### A gate that blocks its own fix
- **Symptom:** the deny message says "add the fields", and the edit that adds them is denied too — the files become uneditable.
- **Why:** the gate checked the edit fragment, not the resulting file; tests covered only "no fields → deny" and "has fields → pass".
- **Right way:** on Edit, simulate the replacement (`old_string→new_string`, honouring `replace_all`) and judge the result; acceptance must include "the path the gate itself suggests is passable". Run your own repair commands through the gate before shipping it.
- **Seen:** once.

### A hook accepted with a different call than production uses
- **Symptom:** the manual test is green, in production the hook is dead (Permission denied), a fail-open wrapper hides it for weeks — only `hook-errors.log` grows.
- **Why:** the test ran `python3 script`, while `settings.json` calls the file as an executable (needs `+x`).
- **Right way:** accept with THE SAME command as in `settings.json`, through [`hook-safe.sh`](../hooks/hook-safe.sh); register new hooks only through the wrapper; after registering, look at the hook error log.
- **Seen:** once — 33 days of a dead hook.

### A hook keyed on `$cwd`
- **Symptom:** a hook "LIVE" for a month that never ran once; or the opposite — it injects another agent's briefing as soon as you `cd` into a foreign folder.
- **Why:** the condition `[[ -f "$cwd/briefing.md" ]] || exit 0`, while sessions start from the root; the session's identity is, by the methodology, its name, not the cwd. When fixing it, the same `$cwd` base was copied — nothing got fixed.
- **Right way:** key on an identity file written per session (`~/.claude/agent-identity/<sid>`); when fixing a dead mechanism, first find out WHY it is dead and don't inherit the cause. "LIVE" only with a marker/injection seen in a real session.
- **Seen:** 3 times.

### Regex backtracking on large heredocs
- **Symptom:** a gate on every Bash call thinks for ~20 s.
- **Why:** backtracking regexes over long heredoc bodies.
- **Right way:** tokenize the command instead of running a regex over raw text (0.03 s after the fix).
- **Seen:** once.

### The event slot is already taken
- **Symptom:** a new hook on `Stop` disables the old one (or vice versa).
- **Why:** another script is registered for the event; replacing it quietly removes the previous function.
- **Right way:** a dispatcher per event (`stop-dispatch.sh` calls everyone), not a replacement.
- **Seen:** once.
- **Another example:** "an agent can be woken only by an explicit call to another agent" — false. A background Bash command (`run_in_background`) wakes the agent in the same tab on exit → a wait script + a Stop gate. Check descriptions of TOOLS too, not only hook events.

### "Can't be mechanized" — said from memory
- **Symptom:** a class of errors is declared "attention only", although a suitable hook event exists.
- **Why:** the answer was given without checking the event list: there are dozens of events (38 at the time), and only 5 were in use.
- **Right way:** before "can't be made impossible", check the list of hook events and what each receives (e.g. `Stop` gets `transcript_path`).
- **Seen:** once.

### `claude -p` from a script inherits the global allow — the "read-only" subagent has Bash
- **Symptom:** a "read-only reviewer" leaves its test lines in your live logs.
- **Why:** `--allowedTools` only ADDS auto-permissions; a global `permissions.allow: ["Bash"]` in settings applies to the child session too. Only `--tools <list>` restricts the set.
- **Right way:** for an isolated subagent always pass `--tools "Read,Grep,Glob"`; verify live — checksum your logs before and after a run.
- **Seen:** once.

### A live test of a hook in the same block of calls as the `settings.json` edit
- **Symptom:** a freshly added gate "did not fire" in practice (the command passed), although a manual run of the same JSON through the script gives deny.
- **Why:** the harness re-reads settings.json asynchronously (a file watcher); a call fired right after in the same block still runs with the old set of hooks.
- **Right way:** edit settings → a separate next call for the live test. For a dangerous gate, use a live target that is harmless even if the gate fails (a non-existent path).
- **Seen:** once.

### A mechanism coarser than the rule cuts those the rule didn't touch
- **Symptom:** a ban "agent sessions must not SSH to the operator's laptop" was implemented as a firewall rule — and it also cut the cron deployer, which was never banned; a release was built, passed the gate, got tagged — and failed at deploy.
- **Why:** the firewall sees packets, not sessions: an agent and a cron job are the same port and the same bytes. The flip side: don't hang a boundary on a VALUE the restricted party can rewrite itself (a permission mode in settings.json) — it opens from inside.
- **Right way:** a mechanism has the same granularity as the rule (a rule about sessions → a hook/classifier that sees sessions). When the rule changes, rewrite the mechanism or RETIRE it; don't leave a second policy layer that diverges from the first.
- **Seen:** once (the guard was retired after two months: unregistered, stale address, softened rule).

### A Bash gate checks the command with grep line by line — a newline hides the second command
- **Symptom:** a "Bash only reads" gate let `ls\nrm -rf X` through (exit 0).
- **Why:** `grep -qE '>|;|&…'` tests EACH line separately, and no single line contained a forbidden character; for the shell `\n` is a command separator just like `;`. The author's classic miss: the test matrix was all single-line.
- **Right way:** the first step of a Bash gate: `case "$cmd" in *$'\n'*|*$'\r'*) deny ;; esac` (or check each line as a separate command). Multi-line cases are mandatory in the test matrix of any command gate.
- **Seen:** once (found in a cross-review).

### Headless `claude -p` with cwd=repo inherits `.claude/settings.local.json` — accumulated "Always allow"
- **Symptom:** a bot's narrow allowlist (`--allowedTools` read-only only) — and yet the bot can run `git checkout/restore/stash` and a deploy script.
- **Why:** `claude -p` picks up project and local settings from the cwd; in a working repo `settings.local.json` accumulates years of "Always allow" clicks from interactive sessions. `--allowedTools` ADDS permissions, it doesn't replace inherited ones.
- **Right way:** any headless `claude -p` with untrusted input (a chat bot, a webhook, mail) runs with `--setting-sources user` (or an explicit `--settings` file), and the restricting hooks go into those user settings. Check: read `permissions.allow` in every `settings*.json` on the path.
- **Seen:** once.

### A Bash gate built as a denylist of metacharacters is leaky by definition
- **Symptom:** a gate "blocks `> ; & $( \``" — and lets through `<(touch x)`, `a || rm b`, `echo $TOKEN`, `${HOME}`, any `rm`/`tee`/`cp`, because they simply aren't on the forbidden list.
- **Why:** the shell has dozens of ways to execute or write; the forbidden can't be enumerated. And a check that ignores quoting either cuts legitimate input (`jq '.[] | {a:.b}'`) or passes what is in double quotes (`"$X"` expands).
- **Right way:** an ALLOWLIST. Parse the command outside quotes → allow only `|`; each segment through `shlex.split`, the first token from a whitelist, for "dangerous" utilities a whitelist of subcommands (git: log/status/diff/show); forbid `$` and backtick everywhere (they are live inside double quotes). Every path argument → realpath → not in secret zones; for recursive ones (`grep -r`, Grep/Glob) also not an ancestor of a secret zone. The gate's wrapper fails closed.
- **Seen:** once (found in a cross-review).

### A child `claude -p` inherits the parent's env — tokens included
- **Symptom:** a bot starts `claude -p` with `env={**os.environ, …}` → the bot's token is in the child process; `echo $BOT_TOKEN` was stopped only by the model's refusal, not by a mechanism.
- **Why:** the child gets the parent's whole environment unless told otherwise.
- **Right way:** an explicit env filter for the child (strip `*TOKEN/*SECRET/*PASSWORD/*API_KEY`, keep only what claude's own authorization needs) + forbid `$` in the Bash gate + a Read gate on `/proc/*/environ`. Verify with a live run: "who refused — the gate or the model?" (stream-json shows `is_error` and the hook's text).
- **Seen:** once.

### After `/compact` the session file can hold TWO conversations — "the last line" isn't necessarily your branch
- **Symptom:** a Stop gate sees "context 700k" right after a compaction, demands a recap again, and blocks the stop of an agent the human didn't address; the agent "doesn't remember" its own work.
- **Why:** a background-task notification that arrived during `/compact` wakes the OLD conversation; it keeps appending to the same .jsonl. The branches are told apart only by the `parentUuid` chain: the live one descends from the last `compact_boundary`, the ghost from the old root. `isSidechain` is false in both.
- **Right way:** a gate that judges "the last turn" takes only lines of the live branch (a `live_branch(transcript)` helper); on a ghost's turn, don't block (a block keeps it alive).
- **Seen:** once.

### A hook blocks with `exit 2`, but is registered through hook-safe — the block silently doesn't apply
- **Symptom:** the error log says "auto-extract-docs.sh failed (exit 2) :: PDF already extracted…"; the agent meanwhile reads the raw PDF and never sees the hint.
- **Why:** `hook-safe.sh` deliberately swallows exit codes (fail-open): to it `exit 2` is a crash, the tool call is let through, stderr goes to the log.
- **Right way:** a hook wrapped in hook-safe refuses only with JSON on stdout (`permissionDecision: deny`) and exit code 0. Verify by effect — feed the event through hook-safe and see the deny, not "the script itself returns 2".
- **Seen:** once.

### A script names its output by timestamp to the second → two parallel runs write one file
- **Symptom:** two `review.sh --model opus … &` started in the same second → both `ts=$(date +%Y%m%d-%H%M%S)` equal → the second overwrote the first, one report lost.
- **Why:** second-resolution time is not unique under parallel launch.
- **Right way:** add the PID to the name (`ts=…-$$`) or use `mktemp` — for any script that names output by time and may run in parallel.
- **Seen:** once.

### A hook recognizes the project by `/claude-projects/Project-X/` — and skips edits in work copies
- **Symptom:** a team's agents edit in `…/claude-projects-wt/<agent>/Project-X/`, not in the main tree. The issue-first detector in a pitfalls hint searched only `/claude-projects/Project-` and would have seen none of the team's edits.
- **Why:** the path pattern assumed one checkout location; git worktrees live elsewhere.
- **Right way:** match `/claude-projects(?:-wt/[^/]+)?/(Project-[\w-]+)/` and cover it with a test. Writing a hook about "a project file"? Start from this pattern.
- **Seen:** once.
