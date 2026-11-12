#!/usr/bin/env bash
# Close an item in YOUR OWN inbox under the SAME lock as delivery. Reason: an agent that clears its inbox with a bare
# Edit/Write (read-modify-write without a lock) wipes letters that arrived in parallel - a lost update, "a lock on the
# door and an open window". This tool holds the flock.
#
# Usage: inbox_done.sh <agent|path-to-inbox.md> <unique substring of the item> [entry for the Processed section]
# rc: 2 addressee · 3 lock · 4 item/section not found · 7 the substring matches several DIFFERENT items (closing
#     "the first" could close an unread one - give a longer substring) · 8 python failed / built an empty file (the
#     inbox is NOT touched: a broken UTF-8 byte once produced an empty inbox written over a live one) · 5 post-check.
# The item (first line + continuation lines) leaves "## New"; on top of "## Processed" (or "## Done") goes your entry,
# or an auto-made `- [x] [date] <first line> - done.` Post-validation FROM DISK: the item is gone from New.

set -euo pipefail
export LC_ALL=C.UTF-8
HERE="$(dirname "$(readlink -f "$0")")"
source "$HERE/inbox_lib.sh"

target="${1:-}"; needle="${2:-}"; done_text="${3:-}"
if [[ -z "$target" || -z "$needle" || "$target" == -h || "$target" == --help ]]; then
    echo "inbox_done.sh <agent|path-to-inbox.md> <unique substring of the item> [entry for Processed]" >&2; exit 2
fi
inbox=$("$HERE/inbox_resolve.sh" "$target") || exit 2
new_hdr=$(find_new_hdr "$inbox"); done_hdr=$(find_done_hdr "$inbox")
# How many lines with the needle are in New BEFORE: the post-validation counts, it does not just look (two identical
# items -> one closed, the other stays -> a false "something overwrote the file").
count_needle() { awk -v hdr="$new_hdr" '$0==hdr{s=1;next} /^## /{s=0} s' "$inbox" | command grep -cF -- "$needle" || true; }
before=$(count_needle)

lock_inbox "$inbox" inbox_done

tmp=$(mktemp "${inbox}.doneXXXX")
rc=0
NEEDLE="$needle" DONE_TEXT="$done_text" NEW_HDR="$new_hdr" DONE_HDR="$done_hdr" python3 - "$inbox" > "$tmp" <<'PYEOF' || rc=$?
import sys, os, re, datetime
needle = os.environ["NEEDLE"]
done_text = os.environ["DONE_TEXT"]
NEW, DONE = os.environ["NEW_HDR"], os.environ["DONE_HDR"]
# surrogateescape: a broken byte in someone else's letter (a preview cut in the middle of a letter) must not break
# the closing, and comes back as it was
sys.stdout.reconfigure(errors="surrogateescape")
lines = open(sys.argv[1], encoding="utf-8", errors="surrogateescape").read().split("\n")

try:
    ni = lines.index(NEW)
except ValueError:
    sys.exit(10)  # no section - do not touch
end = next((i for i in range(ni + 1, len(lines)) if lines[i].startswith("## ")), len(lines))

# all "- [ ]" items that have the needle in the first line or in a continuation
heads = [i for i in range(ni + 1, end) if lines[i].startswith("- [ ]")]
def span(h): return h, next((j for j in heads if j > h), end)
def body(h):
    a, b = span(h); x = lines[a:b]
    while x and not x[-1].strip(): x.pop()
    return x
hits = [h for h in heads if any(needle in l for l in body(h))]
if not hits:
    sys.exit(11)  # item not found
if len({"\n".join(body(h)) for h in hits}) > 1:
    sys.stderr.write("".join(f"  - {lines[h][:160]}\n" for h in hits))
    sys.exit(12)
start, stop = span(hits[0])   # identical duplicates: close one

item = lines[start:stop]
while item and not item[-1].strip(): item.pop()
rest = lines[:start] + lines[stop:]

if not done_text:
    first = re.sub(r"^- \[ \] ", "", item[0])
    done_text = f"- [x] [{datetime.date.today().isoformat()}] {first} - done."

out = rest
try:
    oi = out.index(DONE)
    out = out[:oi + 1] + ["", done_text] + out[oi + 1:]
except ValueError:
    out += ["", DONE, "", done_text]
print("\n".join(out), end="")
PYEOF
case "$rc" in
    0)  ;;
    10) rm -f "$tmp"; echo "inbox_done: no \"$new_hdr\" section in $inbox" >&2; exit 4 ;;
    11) rm -f "$tmp"; echo "inbox_done: no item with \"$needle\" in \"$new_hdr\"" >&2; exit 4 ;;
    12) rm -f "$tmp"; echo "inbox_done: \"$needle\" is in several DIFFERENT items (above) - not guessing which to close. Give a longer substring." >&2; exit 7 ;;
    *)  rm -f "$tmp"; echo "inbox_done: python rc=$rc - inbox NOT touched ($inbox)" >&2; exit 8 ;;
esac
# last line of defence: the assembled file cannot be empty
[[ -s "$tmp" ]] || { rm -f "$tmp"; echo "inbox_done: assembled an empty file - inbox NOT touched ($inbox)" >&2; exit 8; }

chown --reference="$inbox" "$tmp" 2>/dev/null || true
chmod --reference="$inbox" "$tmp" 2>/dev/null || true
mv "$tmp" "$inbox"

# post-validation FROM DISK: the needle occurs in New fewer times than before (duplicates are not an error)
after=$(count_needle)
if [[ "$after" -ge "$before" ]]; then
    echo "inbox_done: 🔴 POST-VALIDATION: the item is still in \"$new_hdr\" ($inbox) - something overwrote the file" >&2
    exit 5
fi
echo "inbox_done: item closed ✓ ($inbox)"
