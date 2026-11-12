#!/usr/bin/env bash
# Atomically add an item to an agent's inbox. The ONLY sanctioned write path into an inbox, for scripts and agents.
# Reason: parallel read-modify-write on shared markdown inboxes collided three times in one day (torn headers, a
# vanished section, a duplicate item).
#
# Usage: inbox_post.sh <agent|path-to-inbox.md> <item text (markdown, may be multi-line)>   (no text -> stdin)
#   agent: folder name under the agents dir, <name> without -agent, or an alias from .aliases (case-insensitive).
# Guarantees: flock (no lost update) · insert RIGHT AFTER the "## New" header · the same item already there is not
#   added twice · no "## New" section -> create it at the end with a loud warning (never silent, never lost) ·
#   post-validation FROM DISK after the move, one repair insert, then the item goes to a pending queue.

set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
source "$HERE/inbox_lib.sh"

case "${1:-}" in
    -h|--help|help|"")   # `--help` used to land in an inbox as the text of a letter
        echo "inbox_post.sh <agent|path-to-inbox.md> <text>   (or the text on stdin)"
        echo "  agent: folder name under the agents dir, <name> without -agent, or an alias from .aliases."
        [[ -z "${1:-}" ]] && exit 2 || exit 0 ;;
esac
target="$1"; shift
text="$*"
# No text arguments -> stdin: single quotes in a shell argument mangle apostrophes and backticks, a heredoc/pipe
# does not.
[[ -n "$text" ]] || text="$(cat)"
[[ -n "$text" ]] || { echo "inbox_post: empty text (neither argument nor stdin)" >&2; exit 2; }

# A text that looks like an option is not a letter (`inbox_post.sh agent --dry-run` once put "--dry-run" into an inbox).
if [[ "$text" == -* && "$text" != "- "* ]]; then
    echo "inbox_post: text \"${text:0:30}\" looks like an option, not a letter - inbox_post has no options (only --help). Not sent." >&2
    exit 2
fi
inbox=$("$HERE/inbox_resolve.sh" "$target") || exit 2

# An item without a leading date gets today's.
[[ "$text" == "- [ ] ["* ]] || text="- [ ] [$(date +%Y-%m-%d)] $text"

lock_inbox "$inbox" inbox_post

# No "## New" section (empty or damaged inbox) -> CREATE it at the end and put the item there. It used to go under a
# "BROKEN STRUCTURE" header, the post-validation looked for it in "New", did not find it, repaired, and the next
# watchman pass re-posted the pending copy: +3 copies every time. Loud: stderr + a line BEFORE the header (outside the
# section, so a "New"-section validator does not complain about it on every prompt).
heal_new() {
    cat "$inbox" > "$1"
    printf '\n⚠ inbox_post %s: the "%s" section was missing - created automatically, check the structure.\n\n%s\n\n%s\n' "$(date '+%F %T')" "$new_hdr" "$new_hdr" "$text" >> "$1"
    echo "inbox_post: ⚠ no \"$new_hdr\" in $inbox - section created at the end, item placed there" >&2
}
new_hdr=$(find_new_hdr "$inbox")
tmp=$(mktemp "${inbox}.postXXXX")
# The item goes through ENVIRON, not `awk -v`: -v interprets escape sequences, so a `\b` from a regex in a letter
# became a backspace, the check never found "its own" text, the repair insert duplicated it and the watchman then
# delivered it again on EVERY prompt (12+ copies once).
insert_into() {   # insert_into <output file>: item right after the header; the first item evicts the placeholder
    if grep -qxF -- "$new_hdr" "$inbox"; then
        ENTRY="$text" awk -v hdr="$new_hdr" '
            /^## /            { in_new = ($0 == hdr) }
            (/^_\(empty\)_$/ || /^_\(порожньо\)_$/) && in_new && injected { next }
            { print }
            $0 == hdr && !injected { print ""; print ENVIRON["ENTRY"]; injected=1 }
        ' "$inbox" > "$1"
    else
        heal_new "$1"
    fi
}
# Idempotent by the WHOLE text (not the first line: two different letters "From X:" can differ only in the body).
_new=$(awk -v hdr="$new_hdr" '$0==hdr{s=1;next} /^## /{s=0} s' "$inbox")
if [[ "$_new" == *"$text"* ]]; then
    rm -f "$tmp"; echo "inbox_post: item already in \"$new_hdr\" - not duplicating"; exit 0
fi
insert_into "$tmp"

# pre-check: the structure did not degrade (the number of "## " sections did not drop)
if [[ $(grep -c '^## ' "$tmp") -lt $(grep -c '^## ' "$inbox") ]]; then
    rm -f "$tmp"; echo "inbox_post: validation FAILED (a section vanished) - file NOT changed" >&2; exit 4
fi

chown --reference="$inbox" "$tmp" 2>/dev/null || true
chmod --reference="$inbox" "$tmp" 2>/dev/null || true
mv "$tmp" "$inbox"

# ── post-validation AFTER mv, reading FROM DISK ──────────────────────────────────────────────────────────────────
# Checking $tmp before mv only proved "we assembled the right file", not "it survived" (a real case: the script said
# OK while the letter vanished in a lost update). Proof of execution, not of configuration: the item must be IN the
# "New" section of the final file on disk. No pipelines with an early exit under pipefail: `printf big | head -1` on a
# letter over 64 KB gives SIGPIPE -> rc 141 AFTER delivery (the sender sees a failure and sends again); `awk | grep -q`
# did the same to the section check -> "not found" for a present letter -> a repair insert -> a duplicate.
first_line=${text%%$'\n'*}
in_new() { FL="$first_line" awk -v hdr="$new_hdr" '$0==hdr{s=1;next} /^## /{s=0} s && index($0,ENVIRON["FL"]){f=1} END{exit !f}' "$inbox"; }
# Waiting does not help: a live session that owns the inbox may rewrite the file for longer than any check window.
# The right move is to RE-INSERT if the item vanished: the insert is idempotent (presence is checked first), a lost
# update is healed by writing again, not by watching.
deliver() {
    in_new && return 0
    # every repair insert leaves a trace, so the next duplicate has evidence: who, where, when.
    mkdir -p "$HOME/.claude" 2>/dev/null
    printf '%s repair-insert pid=%s ppid=%s -> %s :: in file=%s in New=%s inode=%s size=%s :: %s\n' "$(date '+%F %T')" "$$" "$PPID" "$inbox" \
        "$(grep -cF -- "$first_line" "$inbox" 2>/dev/null)" \
        "$(FL="$first_line" awk -v hdr="$new_hdr" '$0==hdr{s=1;next} /^## /{s=0} s && index($0,ENVIRON["FL"]){n++} END{print n+0}' "$inbox")" \
        "$(stat -c %i "$inbox" 2>/dev/null || stat -f %i "$inbox" 2>/dev/null)" "$(wc -c < "$inbox" 2>/dev/null | tr -d ' ')" \
        "$(printf '%s' "$first_line" | python3 -c 'import sys;print(sys.stdin.read()[:100])' 2>/dev/null)" >> "$HOME/.claude/inbox-post-repairs.log" 2>/dev/null || true
    tmp2=$(mktemp "${inbox}.postXXXX")
    insert_into "$tmp2"
    chown --reference="$inbox" "$tmp2" 2>/dev/null || true
    chmod --reference="$inbox" "$tmp2" 2>/dev/null || true
    mv "$tmp2" "$inbox"
    in_new
}
# Limit: 1 initial + 1 repair insert. More means a duplicate storm (5 copies once: the live session that owns the inbox
# edited the file DIRECTLY, bypassing our lock; check-then-insert is not atomic and every "repair" could add one more
# copy that the live session merged).
ok=0
for pause in 0 2; do
    sleep "$pause"
    if deliver; then ok=1; break; fi
done
if [ "$ok" -ne 1 ]; then
    # Delivery guarantee: it did not hold under contention -> the letter goes to a fallback queue next to the inbox
    # for the owner (or whatever delivers pending items) to pick up when the live session lets go of the file.
    # Never lose a letter silently.
    pend_dir="$(dirname "$inbox")/inbox-pending"
    mkdir -p "$pend_dir"
    pf="$pend_dir/$(date +%s)-$$.md"
    printf '%s\n' "$text" > "$pf"
    chown --reference="$inbox" "$pf" 2>/dev/null || true
    echo "inbox_post: 🟡 the item did not stay in \"$new_hdr\" under a parallel rewrite - queued in $pf. Count it as DEFERRED, not lost: move it into the inbox by hand if nothing delivers the queue." >&2
    exit 0
fi
# The addressee is not listening (no alarm, session silent) -> one line to the sender. Delivery and rc do not change.
# Off in tests unless asked for (INBOX_LISTEN=1).
if [[ "${INBOX_LISTEN:-}" == 1 || ( "${HANZ_TEST:-}" != 1 && "${INBOX_LISTEN:-}" != 0 ) ]]; then
    if command -v timeout >/dev/null 2>&1; then timeout 5 "$HERE/agent_listening.py" "$inbox" 2>/dev/null || true
    else "$HERE/agent_listening.py" "$inbox" 2>/dev/null || true; fi
fi
