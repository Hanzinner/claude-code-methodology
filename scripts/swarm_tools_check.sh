#!/usr/bin/env bash
# swarm_tools_check.sh - nightly check that the tools catalog (SWARM-TOOLS.md) has not gone stale.
# A script in <claude dir>/scripts (not *.bak*, *.log, *.pyc, folders) or an executable in <claude dir>/bin whose name
# (without extension) is not mentioned in the catalog -> ONE letter to CCM_SWARM_TOOLS_OWNER (empty = log only).
# The same list already waiting in the owner's "## New" section is not posted again (three identical letters in
# three days once). Nothing missing -> one log line (proof that the check is alive).
# Catalog: CCM_SWARM_TOOLS (default <workspace>/SWARM-TOOLS.md); no catalog -> exit 0.
# Cron: 50 12 * * * . Test overrides: SWARM_TOOLS_INBOX, SWARM_TOOLS_DIRS (colon-separated).
set -uo pipefail
export LC_ALL=C.UTF-8
HERE=$(dirname "$(readlink -f "$0")")
eval "$(python3 "$HERE/../lib/ccm_conf.py" --shell)"
CAT="${CCM_SWARM_TOOLS:-$CCM_WORKSPACE/SWARM-TOOLS.md}"
OWNER="${CCM_SWARM_TOOLS_OWNER:-}"
POST="${CCM_INBOX_POST:-$HERE/inbox_post.sh}"
DIRS="${SWARM_TOOLS_DIRS:-$CCM_CLAUDE_DIR/scripts:$CCM_CLAUDE_DIR/bin}"
[[ -f "$CAT" ]] || exit 0
miss=()
IFS=: read -ra D <<< "$DIRS"
for d in "${D[@]}"; do
    [[ -d "$d" ]] || continue
    for f in "$d"/*; do
        [[ -f "$f" ]] || continue
        n=$(basename "$f")
        case "$n" in *.bak*|*.log|*.pyc|*.new|*.tmp|.*) continue ;; esac
        [[ "$d" == */bin && ! -x "$f" ]] && continue
        grep -qF -- "${n%.*}" "$CAT" || miss+=("$n")
    done
done
((${#miss[@]})) || { echo "$(date '+%F %T') swarm_tools_check: every script is in the catalog"; exit 0; }
if [[ -n "$OWNER" ]]; then
    INBOX=${SWARM_TOOLS_INBOX:-$("$HERE/inbox_resolve.sh" "$OWNER" 2>/dev/null)}
    if [[ -n "$INBOX" && -f "$INBOX" ]] && NEEDLE="- ${miss[*]}." awk '/^## (New|Нові)/{s=1;next} /^## /{s=0} s && index($0,"swarm_tools_check:") && index($0,ENVIRON["NEEDLE"]){f=1} END{exit !f}' "$INBOX" 2>/dev/null; then
        echo "$(date '+%F %T') swarm_tools_check: ${#miss[@]} without a line - letter already waiting, not repeating"; exit 0
    fi
fi
echo "$(date '+%F %T') swarm_tools_check: ${#miss[@]} without a line${OWNER:+ -> $OWNER}"
if [[ -n "$OWNER" ]]; then
    "$POST" "$OWNER" "- [ ] [$(date +%F)] swarm_tools_check: ${#miss[@]} script(s) without a line in SWARM-TOOLS.md - ${miss[*]}. Add a line (what it does, when) or remove the script." >/dev/null \
        || { echo "$(date '+%F %T') swarm_tools_check: WARNING letter NOT sent (rc $?)"; exit 1; }
fi
