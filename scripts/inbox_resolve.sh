#!/usr/bin/env bash
# inbox_resolve.sh <agent|path-to-inbox.md> -> prints the path of the agent's inbox.md; error -> stderr + exit 2.
# The ONE place that decides "who is the addressee", shared by inbox_post.sh, inbox_done.sh and inbox_wait.sh (two
# copies of this logic once drifted apart: one knew aliases, the other did not, and a letter to a renamed agent
# was lost). Lookup order: a file path -> folder <name> -> folder <name>-agent (also one level down, in
# group folders) -> an alias listed in <agent folder>/.aliases (one name per line, case-insensitive).
# More than one match -> exit 2 listing the candidates; nothing is guessed.
set -uo pipefail
source "$(dirname "$(readlink -f "$0")")/inbox_lib.sh"
target="${1:-}"
[[ -n "$target" ]] || { echo "inbox_resolve: empty addressee" >&2; exit 2; }
if [[ -f "$target" ]]; then
    inbox="$target"
else
    # lower-casing in Python: `tr` works on bytes and does not know non-ASCII letters
    low=$(T="$target" python3 -c 'import os;print(os.environ["T"].strip().lower())')
    shopt -s nullglob
    hits=()
    for c in "$AGENTS_ROOT/$target" "$AGENTS_ROOT"/*/"$target" "$AGENTS_ROOT/$target-agent" "$AGENTS_ROOT"/*/"$target-agent"; do
        [[ -f "$c/inbox.md" ]] && hits+=("$c/inbox.md")
    done
    if [[ ${#hits[@]} -eq 0 ]]; then
        mapfile -t hits < <(R="$AGENTS_ROOT" L="$low" python3 -c '
import glob, os
R, L = os.environ["R"], os.environ["L"]
for a in sorted(glob.glob(R + "/*/.aliases") + glob.glob(R + "/*/*/.aliases")):
    names = {l.strip().lower() for l in open(a, encoding="utf-8", errors="replace").read().split("\n")
             if l.strip() and not l.startswith("#")}
    ib = os.path.join(os.path.dirname(a), "inbox.md")
    if L in names and os.path.isfile(ib):
        print(ib)')
    fi
    if [[ ${#hits[@]} -gt 0 ]]; then
        mapfile -t hits < <(printf '%s\n' "${hits[@]}" | awk 'NF && !seen[$0]++')
    fi
    if [[ ${#hits[@]} -eq 0 ]]; then
        echo "inbox: no inbox found for '$target' (looked for a folder, <name>-agent and .aliases in $AGENTS_ROOT)" >&2; exit 2
    elif [[ ${#hits[@]} -gt 1 ]]; then
        echo "inbox: '$target' is ambiguous, candidates: $(printf '%s ' "${hits[@]%/inbox.md}")" >&2; exit 2
    fi
    inbox="${hits[0]}"
fi
printf '%s\n' "$inbox"
