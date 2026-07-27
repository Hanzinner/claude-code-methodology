#!/usr/bin/env bash
# Atomically append an item to an agent's inbox. The ONLY sanctioned write path
# for scripts (and agents). Reason: parallel read-modify-write on shared markdown
# inboxes collided three times in one day (torn headers, a vanished section, a
# duplicate). See docs/multi-agent.md ("shared things have no owner").
#
# Usage: inbox-post.sh <agent|path-to-inbox.md> <item text (markdown, may be multi-line)>
#   agent — a folder name under the agents root (exact, no fuzzy), or a ready path.
# Guarantees: flock (no lost update) · inserts right after "## New" ·
#   no anchor -> append at the end with a loud marker (never silent, never lost).
#
# Config: CLAUDE_AGENTS_ROOT (default: $HOME/claude-projects/Agents)

set -euo pipefail

AGENTS_ROOT="${CLAUDE_AGENTS_ROOT:-$HOME/claude-projects/Agents}"

target="$1"; shift
text="$*"
[[ -n "$text" ]] || { echo "inbox-post: empty text" >&2; exit 2; }

if [[ -f "$target" ]]; then
    inbox="$target"
elif [[ -f "$AGENTS_ROOT/$target/inbox.md" ]]; then
    inbox="$AGENTS_ROOT/$target/inbox.md"
else
    # container folders (Agents/<group>/<agent>)
    hits=("$AGENTS_ROOT"/*/"$target"/inbox.md)
    [[ -f "${hits[0]}" && ${#hits[@]} -eq 1 ]] \
        || { echo "inbox-post: no inbox found for '$target'" >&2; exit 2; }
    inbox="${hits[0]}"
fi

# Item without a leading date -> prepend today's
[[ "$text" == "- [ ] ["* ]] || text="- [ ] [$(date +%Y-%m-%d)] $text"

# Lock a SEPARATE stable file, not the inbox itself: mv swaps the inbox's inode,
# so two writers could hold locks on different inodes (a race). Nobody mv's .lock.
exec 9>>"${inbox}.lock"
flock -w 15 9 || { echo "inbox-post: lock timeout on $inbox" >&2; exit 3; }

tmp=$(mktemp "${inbox}.postXXXX")
new_hdr='## New'
grep -q '^## New candidates$' "$inbox" && new_hdr='## New candidates'
if grep -q "^${new_hdr}\$" "$inbox"; then
    # insert after the header; the first item evicts the "_(empty)_" placeholder
    awk -v entry="$text" -v hdr="$new_hdr" '
        /^## /            { in_new = ($0 == hdr) }
        /^_\(empty\)_$/ && in_new && injected { next }
        { print }
        $0 == hdr && !injected { print ""; print entry; injected=1 }
    ' "$inbox" > "$tmp"
else
    cat "$inbox" > "$tmp"
    printf '\n## ⚠ BROKEN STRUCTURE — no "## New" section found, item appended at the end\n\n%s\n' "$text" >> "$tmp"
fi

# pre-check: structure didn't degrade (the "## " section count didn't drop)
if [[ $(grep -c '^## ' "$tmp") -lt $(grep -c '^## ' "$inbox") ]]; then
    rm -f "$tmp"; echo "inbox-post: validation FAILED (a section vanished) — file NOT changed" >&2; exit 4
fi

chown --reference="$inbox" "$tmp" 2>/dev/null || true
chmod --reference="$inbox" "$tmp" 2>/dev/null || true
mv "$tmp" "$inbox"

# post-validation AFTER mv, reading FROM DISK. Checking $tmp before mv only proved
# "we assembled the right file", not "it survived" (a real case: the script said ✓
# while the item vanished in a lost update). Proof of execution, not of config:
# the item must be IN the "New" section of the final on-disk file.
first_line=$(printf '%s\n' "$text" | head -1)
if ! awk -v hdr="${new_hdr:-## New}" '$0==hdr{s=1;next} /^## /{s=0} s' "$inbox" | grep -qF -- "$first_line"; then
    echo "inbox-post: 🔴 POST-VALIDATION FAILED — item NOT found in the 'New' section on disk ($inbox). Not delivered (possibly a concurrent overwrite). Do NOT report 'sent'." >&2
    exit 5
fi
