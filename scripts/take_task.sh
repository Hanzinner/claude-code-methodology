#!/usr/bin/env bash
# take_task.sh <project> <story-code> — "I take task N": writes into the session state what the agent is working on, so
# that a code edit inside a project folder has a task number (issue first). While tasks aren't kept as data, a task =
# a story in <workspace>/<project folder>/ROADMAP.md. The session id comes from the nearest ancestor `claude` process
# (~/.claude/sessions/<pid>.json). A detector (hooks/code-pitfalls-hint.py) can read ~/.claude/task-taken/<sid>;
# for now it is a journal.
# Project folders: config CCM_PROJECTS_GLOB (default "Project-*", relative to CCM_WORKSPACE); the project may be given
# with or without the folder prefix ("Shop" or "Project-Shop").
# Overrides for tests: TAKE_TASK_REPO (workspace), TAKE_TASK_SID, TAKE_TASK_STATE (state dir).
set -euo pipefail
eval "$(python3 "$(dirname "$(readlink -f "$0")")/../lib/ccm_conf.py" --shell 2>/dev/null)" || true
proj=${1:?project}; code=${2:?story code}
R=${TAKE_TASK_REPO:-${CCM_WORKSPACE:-$HOME/claude-projects}}
glob=${CCM_PROJECTS_GLOB:-Project-*}
prefix=${glob%%\**}                       # "Project-*" -> "Project-"
proj=${proj#"$prefix"}
name="$prefix$proj"
rm_=$R/$name/ROADMAP.md
[[ -f "$rm_" ]] || { echo "⛔ no $rm_"; exit 4; }
grep -qE "(\[|[^0-9A-Za-z])$code([^0-9]|\])" "$rm_" || { echo "⛔ story $code is not in $rm_ — add it there or take an existing one"; exit 4; }
sid=""
p=$$
while [[ $p -gt 1 ]]; do
    if [[ "$(cat /proc/$p/comm 2>/dev/null)" == claude || -f "$HOME/.claude/sessions/$p.json" ]]; then
        sid=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['sessionId'])" "$HOME/.claude/sessions/$p.json" 2>/dev/null || true)
        break
    fi
    p=$(awk '{print $4}' /proc/$p/stat 2>/dev/null || echo 1)
done
sid=${TAKE_TASK_SID:-$sid}
[[ -n "$sid" ]] || { echo "⛔ could not find the session (run it from the agent's tab)"; exit 2; }
D=${TAKE_TASK_STATE:-$HOME/.claude/task-taken}; mkdir -p "$D"
printf '%s %s %s\n' "$name" "$code" "$(date '+%F %H:%M')" > "$D/$sid"
echo "✅ taking $name $code (session ${sid:0:8})"
