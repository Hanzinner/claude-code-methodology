#!/usr/bin/env bash
# git_empty_objects_check.sh - integrity watchdog: ZERO-BYTE files in .git/objects = a write was cut off (a hard power-off
# in the middle of `git commit` once left 4 empty objects, HEAD's commit among them).
# Found -> it does NOT repair; letter to CCM_GIT_KEEPER (empty = none), once per NEW set (state file), exit 1.
# Clean -> exit 0 and the state is cleared. No .git/objects -> exit 3.
# Run: @reboot + from the supervisor every few minutes. Settings: REPO (default CCM_WORKSPACE), STATE.
set -uo pipefail
HERE=$(dirname "$(readlink -f "$0")")
eval "$(python3 "$HERE/../lib/ccm_conf.py" --shell)"
REPO=${REPO:-$CCM_WORKSPACE}; TO=${CCM_GIT_KEEPER:-}
POST="${CCM_INBOX_POST:-$HERE/inbox_post.sh}"
STATE=${STATE:-$HOME/.claude/supervisor/git-empty-objects.last}
[[ -d "$REPO/.git/objects" ]] || { echo "no $REPO/.git/objects"; exit 3; }
found=$(find "$REPO/.git/objects" -type f -empty 2>/dev/null | sed "s#^$REPO/##" | sort)
if [[ -z "$found" ]]; then echo "no empty objects"; rm -f "$STATE"; exit 0; fi
n=$(printf '%s\n' "$found" | wc -l); sig=$(printf '%s' "$found" | md5sum | cut -c1-12)
echo "empty objects: $n"
if [[ -n "$TO" && "$(cat "$STATE" 2>/dev/null)" != "$sig" ]]; then
  mkdir -p "$(dirname "$STATE")"
  { printf -- "- [ ] [%s] git_empty_objects_check: **%s empty git objects in %s.** Probably a cut-off write (hard power-off). NOT repaired. List:\n" "$(date '+%F %H:%M')" "$n" "$REPO"
    printf '%s\n' "$found" | head -20 | sed 's/^/  - `/; s/$/`/'; } | "$POST" "$TO" >/dev/null && echo "$sig" > "$STATE"
fi
exit 1
