#!/usr/bin/env bash
# Atomically append an item to an agent's inbox. The ONLY sanctioned write path
# for scripts (and agents). Reason: parallel read-modify-write on shared markdown
# inboxes collided three times in one day (torn headers, a vanished section, a
# duplicate). See docs/multi-agent.md ("shared things have no owner").
#
# Usage: inbox-post.sh <agent|path-to-inbox.md> [item text]   (no text -> read stdin)
#   agent — a folder name under the agents root (exact, no fuzzy), or a ready path.
# Guarantees: flock (no lost update) · inserts right after "## New" · an identical
#   item already in New is not added twice · no "## New" section -> create it at the
#   end, loudly, and put the item there · post-validates from disk; one repair
#   re-insert if the item vanished; still gone -> exit 5 (never reports a false "sent").
#
# Config: CLAUDE_AGENTS_ROOT (default: $HOME/claude-projects/Agents)

set -euo pipefail

AGENTS_ROOT="${CLAUDE_AGENTS_ROOT:-$HOME/claude-projects/Agents}"

target="$1"; shift
text="$*"
# No text argument -> stdin (heredoc/pipe survives apostrophes and backticks that
# single-quoted shell arguments mangle).
[[ -n "$text" ]] || text="$(cat)"
[[ -n "$text" ]] || { echo "inbox-post: empty text (neither argument nor stdin)" >&2; exit 2; }

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

new_hdr='## New'
grep -q '^## New candidates$' "$inbox" && new_hdr='## New candidates'

# No "## New" section (empty or damaged inbox) -> create it at the end and put the
# item there, so the post-validation below can find it. Loud: stderr + a note line.
heal_new() {
    cat "$inbox" > "$1"
    printf '\n> inbox-post %s: no "%s" section was found — created automatically, check the structure.\n\n%s\n\n%s\n' \
        "$(date '+%F %T')" "$new_hdr" "$new_hdr" "$text" >> "$1"
    echo "inbox-post: no '$new_hdr' in $inbox — section created at the end, item placed there" >&2
}
# ENTRY via ENVIRON, not `awk -v`: -v interprets escape sequences, so a "\b" in the
# text became a backspace and the post-validation never found its own item.
insert_into() {
    if grep -q "^${new_hdr}\$" "$inbox"; then
        # insert after the header; the first item evicts the "_(empty)_" placeholder
        ENTRY="$text" awk -v hdr="$new_hdr" '
            /^## /            { in_new = ($0 == hdr) }
            /^_\(empty\)_$/ && in_new && injected { next }
            { print }
            $0 == hdr && !injected { print ""; print ENVIRON["ENTRY"]; injected=1 }
        ' "$inbox" > "$1"
    else
        heal_new "$1"
    fi
}
new_section() { awk -v hdr="$new_hdr" '$0==hdr{s=1;next} /^## /{s=0} s' "$inbox"; }

# Idempotent by the WHOLE text: the same item already in New -> nothing to do.
if [[ "$(new_section)" == *"$text"* ]]; then
    echo "inbox-post: item already in '$new_hdr' — not duplicating"; exit 0
fi

tmp=$(mktemp "${inbox}.postXXXX")
insert_into "$tmp"

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
in_new() { new_section | grep -qF -- "$first_line"; }
# A live session that rewrites the file can outlast any wait, so the fix for a lost
# update is to re-insert (idempotent: presence is checked first), not to watch.
# Limit: one repair. More repairs against a concurrent writer breed duplicates.
if ! in_new; then
    tmp2=$(mktemp "${inbox}.postXXXX")
    insert_into "$tmp2"
    chown --reference="$inbox" "$tmp2" 2>/dev/null || true
    chmod --reference="$inbox" "$tmp2" 2>/dev/null || true
    mv "$tmp2" "$inbox"
fi
if ! in_new; then
    echo "inbox-post: 🔴 POST-VALIDATION FAILED — item NOT found in '$new_hdr' on disk ($inbox) after a repair insert. Not delivered (a concurrent writer keeps overwriting). Do NOT report 'sent'." >&2
    exit 5
fi
