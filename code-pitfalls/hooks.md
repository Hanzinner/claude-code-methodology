# hooks

### A defensive hook that fails open: missing dependency → everything allowed
- **Symptom:** the guard is "installed" and lets anything through.
- **Why:** it parsed its input with a tool that wasn't on the machine → crashed on every call → `exit 0` → ALLOWED. In defensive code an error silently becomes permission.
- **Right way:** blocking gates fail CLOSED; before registering one, feed it broken input — remove the dependency, send garbage, cut it off — and check it doesn't wave everything through.

### A gate that blocks its own fix
- **Symptom:** the deny message says "add the fields", and the edit that adds them is denied too — the files become uneditable.
- **Why:** the gate checked the edit fragment, not the resulting file; tests covered only "no fields → deny" and "has fields → pass".
- **Right way:** on Edit, simulate the replacement and judge the result; acceptance must include "the path the gate itself suggests is passable". Run your own repair commands through the gate before shipping it.

### `claude -p` from a script inherits the global allow — the "read-only" subagent has Bash
- **Symptom:** a "read-only reviewer" leaves its test lines in your live logs.
- **Why:** `--allowedTools` only ADDS auto-permissions; a global `permissions.allow: ["Bash"]` in settings applies to the child session too. Only `--tools <list>` restricts the set.
- **Right way:** for an isolated subagent always pass `--tools "Read,Grep,Glob"`; verify live — checksum your logs before and after a run.

### A hook's matcher reads the whole command, heredoc body included
- **Symptom:** a hint keyed on `ssh`/`git` in a Bash command fires when you merely *write a file* that mentions those words.
- **Why:** the command string contains the heredoc body; a regex over the full string can't tell "runs ssh" from "writes a document about ssh".
- **Right way:** strip heredoc bodies and quoted strings before matching, or accept it as noise and rate-limit it (dedup per hour).
