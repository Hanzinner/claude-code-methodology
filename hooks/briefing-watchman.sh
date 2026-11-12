#!/usr/bin/env bash
# UserPromptSubmit hook — the per-prompt watchman of a swarm. On every prompt of an agent session it:
#
#   0. delivers deferred letters (<agent>/inbox-pending/*.md, left by inbox_post.sh when the inbox was busy) to their
#      inbox through scripts/inbox_post.sh, from ANY session — the pending dir sits in the addressee's folder, and
#      the session that finds it is usually someone else's (a letter written = a letter delivered was a bug class);
#   1. RESOLVES THE AGENT (identity): ~/.claude/agent-identity/<session_id> holds the agent's folder. Written when
#      the human's first prompt is (essentially) the agent's name — "<name>" in <agents dir>/<name>/briefing.md —
#      or when the session starts inside an agent's folder. Later `cd` into a neighbour's folder doesn't change who you are;
#   2. BOOTSTRAPS a missing inbox.md, agent-TODO.md, human-TODO.md (creates only, never overwrites);
#   3. re-injects briefing.md whenever its CONTENT changed (hash, not mtime: a git pull/touch would false-inject);
#   4. lists the HANGING inbox items (only the open `- [ ]` ones in "## New", never a dump) on EVERY prompt until they
#      are moved to the closed section ("## Processed"); marks an item older than 2 days; shouts if the new-letters section has a malformed line (an item without
#      the `- [ ]` marker does not exist for any mechanism: two tasks vanished that way for 3 days);
#   5. CODER MODE: a file `.watchlist` in the agent's folder (a path per line, relative to the workspace or absolute,
#      `#` comments) -> shows only the DELTA of those shared files since the last time it showed them (agents talk
#      through shared repo files; the addressee wouldn't learn they were written to). A snapshot, not `git diff HEAD`:
#      changes arrive already committed, so a diff against HEAD would be empty;
#   6. optional dead-man line: CCM_SUPERVISOR_HEARTBEAT = a file the swarm supervisor touches (epoch seconds inside);
#      older than 60 min -> one line. Empty (default) = off.
# Flag texts of Stop detectors are NOT printed here — hooks/surface-flags.sh does that for any ~/.claude/<x>-flags/<sid>.
# Silent when the session is not an agent's or nothing changed. Fails open (exit 0).
#
# Config: CCM_WORKSPACE, CCM_AGENTS_DIR (default <workspace>/Agents), CCM_TRASH_DIR, CCM_SUPERVISOR_HEARTBEAT.
# Supersedes multi-agent/briefing-watchman.sh.

# Every cut goes through u8: a byte cut (head -c, cut -c) in the middle of a letter produced broken UTF-8 that an
# agent copied into a letter and the inbox script choked on it.
u8() { iconv -f utf-8 -t utf-8 -c 2>/dev/null || true; }
set -eu   # no pipefail: `head -1` after grep sends SIGPIPE to the left side of a pipe on a big input — pipefail killed the WHOLE hook
export LC_ALL=C.UTF-8   # so ${s,,} lowercases non-ASCII names (aliases) regardless of the hook's env

eval "$(python3 "$(dirname "$(readlink -f "$0")")/../lib/ccm_conf.py" --shell 2>/dev/null)" || true
WORKSPACE="${CCM_WORKSPACE:-$HOME/claude-projects}"
AGENTS_ROOT="${CCM_AGENTS_DIR:-$WORKSPACE/Agents}"
TRASH="${CCM_TRASH_DIR:-$HOME/.claude-trash}"
SCRIPTS="$(cd "$(dirname "$(readlink -f "$0")")/../scripts" 2>/dev/null && pwd || true)"
# section names come from the inbox group's shared helper (find_new_hdr / find_done_hdr); fallback = the template names
if [[ -f "$SCRIPTS/inbox_lib.sh" ]]; then source "$SCRIPTS/inbox_lib.sh" 2>/dev/null || true; fi
type find_new_hdr >/dev/null 2>&1 || find_new_hdr() { echo "## New"; }
type find_done_hdr >/dev/null 2>&1 || find_done_hdr() { echo "## Processed"; }
MARKER_DIR="$HOME/.claude/briefing-watchman"
IDENTITY_DIR="$HOME/.claude/agent-identity"
mkdir -p "$MARKER_DIR" "$IDENTITY_DIR"

input=$(cat)
session_id=$(echo "$input" | grep -oP '"session_id"\s*:\s*"\K[^"]+' | head -1)
cwd=$(echo "$input" | grep -oP '"cwd"\s*:\s*"\K[^"]+' | head -1)

[[ -z "$session_id" || -z "$cwd" ]] && exit 0

# ── 0. deferred letters -> the addressee, from any session. inbox_post.sh is idempotent, so parallel watchmen don't duplicate.
shopt -s nullglob
for pdir in "$AGENTS_ROOT"/*/inbox-pending "$AGENTS_ROOT"/*/*/inbox-pending "$cwd/inbox-pending"; do
    [[ -d "$pdir" && -f "$(dirname "$pdir")/inbox.md" && -x "$SCRIPTS/inbox_post.sh" ]] || continue
    for pf in "$pdir"/*.md; do
        [[ -f "$pf" ]] || continue
        if "$SCRIPTS/inbox_post.sh" "$(dirname "$pdir")/inbox.md" < "$pf" >/dev/null 2>&1; then
            mkdir -p "$TRASH/inbox-pending-delivered" 2>/dev/null
            mv -f "$pf" "$TRASH/inbox-pending-delivered/" 2>/dev/null || true
            echo "📬 [watchman] delivered a deferred letter -> $(basename "$(dirname "$pdir")") (from inbox-pending)."
        fi
    done
    rmdir "$pdir" 2>/dev/null || true
done
shopt -u nullglob

# ── 6. dead-man line of the supervisor (optional)
hb_="${CCM_SUPERVISOR_HEARTBEAT:-}"
if [[ -n "$hb_" && -f "$hb_" ]]; then
    hb_age_=$(( ( $(date +%s) - $(cat "$hb_" 2>/dev/null || echo 0) ) / 60 ))
    if (( hb_age_ > 60 )); then
        echo "⚠️ [supervisor] The swarm supervisor has been silent for ${hb_age_} min (its cron job isn't running?) — check it ($hb_)."
    fi
fi

# ── 1. AGENT IDENTITY ----------------------------------------------------------
#
# The obvious gate `[[ -f $cwd/briefing.md ]] || exit 0` is wrong when the human never starts a session from an agent's
# folder (cwd is always the workspace root): the hook would never fire. So the name of the agent in the first prompt
# is the activation. Order:
#   1. ~/.claude/agent-identity/<sid> exists and the folder is alive -> work from it (FIRST: an agent that `cd`s into a
#      neighbour's folder stays itself);
#   2. cwd has briefing.md -> cwd mode, and WRITE the identity (a later `cd` doesn't change "who I am");
#   3. else a NARROW match of the prompt against <agents dir>/*/ and */*/ that have briefing.md: the prompt must
#      essentially BE the name (<= 40 chars). Normalization: lowercase, no -_/space, +-suffix "agent", +-tail v<N>
#      ("Foo-Bar V2" -> foobar). Exactly one match -> record the identity. Several/none -> exit quietly, so a mid-work
#      mention of another agent doesn't hijack the session.

identity_file="$IDENTITY_DIR/$session_id"

norm_name() {
    local s prev
    s="${1,,}"                      # NOT tr: tr doesn't lowercase non-ASCII
    s=$(printf '%s' "$s" | tr -d ' _-')
    # Strip suffixes in a LOOP, because the order varies: "foo-agent V2" -> v2 comes off first, THEN agent.
    # A fixed order (agent, then v<N>) gave fooagent != foo — a miss on the real name used for new generations.
    prev=""
    while [[ "$s" != "$prev" ]]; do
        prev="$s"
        s=$(printf '%s' "$s" | sed -E 's/v[0-9]+$//')
        s="${s%agent}"
    done
    printf '%s' "$s"
}

agent_dir=""
id_dir=$(cat "$identity_file" 2>/dev/null || true)
# A folder was renamed: the old name sits in .aliases of the new one -> rewrite the identity, because many mechanisms
# read it (work-guard, alarms, watchers) and each would look for a dead folder.
if [[ -n "$id_dir" && ! -f "$id_dir/briefing.md" ]]; then
    moved=$(OLD="$(basename "$id_dir")" R="$AGENTS_ROOT" python3 -c '
import glob, os
old, R = os.environ["OLD"].lower(), os.environ["R"]
hits = [os.path.dirname(a) for a in glob.glob(R + "/*/.aliases") + glob.glob(R + "/*/*/.aliases")
        if old in {l.split("#")[0].strip().lower() for l in open(a, encoding="utf-8", errors="replace")}]
print(hits[0] if len(hits) == 1 else "")' 2>/dev/null || true)
    if [[ -n "$moved" && -f "$moved/briefing.md" ]]; then
        echo "$moved" > "$identity_file" 2>/dev/null || true
        id_dir="$moved"
    fi
fi
if [[ -n "$id_dir" && -f "$id_dir/briefing.md" ]]; then
    agent_dir="$id_dir"
elif [[ -f "$cwd/briefing.md" ]]; then
    agent_dir="$cwd"
    echo "$agent_dir" > "$identity_file" 2>/dev/null || true
else
    prompt=$(printf '%s' "$input" \
        | python3 -c 'import sys,json;print(json.load(sys.stdin).get("prompt",""))' \
        2>/dev/null || true)
    prompt=$(printf '%s' "$prompt" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    if [[ -n "$prompt" && "${#prompt}" -le 40 && "$prompt" != *$'\n'* ]]; then
        want=$(norm_name "$prompt")
        if [[ -n "$want" ]]; then
            matches=()
            for d in "$AGENTS_ROOT"/*/ "$AGENTS_ROOT"/*/*/; do
                [[ -f "$d/briefing.md" ]] || continue
                [[ "$(basename "$d")" == _* ]] && continue      # _example-agent and other templates are not agents
                hit=0
                [[ "$(norm_name "$(basename "$d")")" == "$want" ]] && hit=1
                # .aliases: the human may call an agent in plain words — a variant per line; the same normalization;
                # more than one match among agents -> stay quiet
                if [[ "$hit" == "0" && -f "$d/.aliases" ]]; then
                    while IFS= read -r al || [[ -n "$al" ]]; do
                        al="${al%%#*}"
                        al=$(printf '%s' "$al" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
                        [[ -z "$al" ]] && continue
                        [[ "$(norm_name "$al")" == "$want" ]] && { hit=1; break; }
                    done < "$d/.aliases"
                fi
                [[ "$hit" == "1" ]] && matches+=("${d%/}")
            done
            if [[ "${#matches[@]}" -eq 1 ]]; then
                agent_dir="${matches[0]}"
                echo "$agent_dir" > "$identity_file"
            fi
        fi
    fi
fi

[[ -z "$agent_dir" ]] && exit 0

brief="$agent_dir/briefing.md"
agent_name=$(basename "$agent_dir")
inbox="$agent_dir/inbox.md"

# ── 2. BOOTSTRAP. A TODO file is created only when the folder has NO such file under any name (agents keep tasks in
# files with other names; a bootstrap that dropped a "right" empty one each time doubled the files).
has_todo() {  # has_todo <glob...> — at least one file exists (case ignored)
    local g f; shopt -s nullglob nocaseglob
    for g in "$@"; do for f in "$agent_dir"/$g; do
        [[ -f "$f" ]] || continue
        # for the agent's own TODO the human's files don't count (*-todo.md would catch a fresh human-TODO.md)
        [[ "${HAS_TODO_SKIP_HUMAN:-0}" == 1 && ( "${f,,}" == *human* ) ]] && continue
        shopt -u nullglob nocaseglob; return 0
    done; done
    shopt -u nullglob nocaseglob; return 1
}

if [[ ! -f "$inbox" ]]; then
    cat > "$inbox" <<TPL
# $agent_name — inbox

> Other agents write here only through \`scripts/inbox_post.sh <agent> "<text>"\` (a lock, and a check that the item
> really landed). The owner reads, does it now or moves it to its todo, and moves the item to \`## Processed\` with a date.
> Keep \`## New\` thin: it is re-shown on every prompt while items hang there. An empty inbox is normal.

## New

## Processed
TPL
fi

if ! has_todo '*human-todo*.md' '*human_todo*.md'; then
    cat > "$agent_dir/human-TODO.md" <<TPL
# $agent_name — waiting for the human

> Only what passes the test: taste / product / priority / irreversible, and "if the human decided the
> opposite, something would change". One line each: 🎯 a decision needed · 👁 something to check by eye.

## Open

## Closed
TPL
fi

if ! HAS_TODO_SKIP_HUMAN=1 has_todo '*agent-todo*.md' 'todo*.md' '*-todo.md' '*_todo.md'; then
    cat > "$agent_dir/agent-TODO.md" <<TPL
# $agent_name — open loops

> This agent's own unfinished work. Read at the start of every session and say out loud what hangs:
> saving a task is not the same as coming back to it. "Later" from the human -> one line here before switching.

## Open

## Closed
TPL
fi

# ── 3. Helper: check-and-inject one watched file. Args: <file> <marker-suffix> <header>
check_and_inject() {
    local file="$1" suffix="$2" header="$3"
    local marker="$MARKER_DIR/${session_id}-${suffix}.hash"
    local current_hash prev_hash=""

    [[ -f "$file" ]] || return 0
    current_hash=$(sha256sum "$file" | awk '{print $1}')
    [[ -f "$marker" ]] && prev_hash=$(cat "$marker" 2>/dev/null || true)
    [[ "$current_hash" == "$prev_hash" ]] && return 0

    {
        if [[ -z "$prev_hash" ]]; then
            echo "[watchman] $header — first shown in this session:"
        else
            echo "[watchman] ⚠ $header — updated, current version below:"
        fi
        echo ""
        echo "--- BEGIN $(basename "$file") ($agent_dir) ---"
        cat "$file"
        echo "--- END $(basename "$file") ---"
    }
    echo "$current_hash" > "$marker"
}

check_and_inject "$brief" briefing "Your briefing.md"

# ── 4. INBOX: a persistent reminder, never a dump. the closed section only grows, so "a thin inbox" was an illusion. While
# `- [ ]` items hang in "## New" we inject ONLY those (with their continuation lines) on EVERY prompt until they are
# moved to the closed section ("## Processed"). An inbox is a to-do, not a doorbell: a one-time injection on a hash change lost items put there
# long ago or by another session. Empty -> silence.

if [[ -f "$inbox" ]]; then
    # Age of an item: one that has lain >= 2 days gets "(lying N d)" — not a block, not hiding, a mark of suspicion so the
    # agent checks it is still true before acting. A date that doesn't parse -> silent.
    now_epoch=$(date +%s)
    newh=$(find_new_hdr "$inbox")
    unproc=$(awk -v NEWH="$newh" '
        $0 == NEWH {sect=1; next}
        /^## /           {sect=0}
        !sect            {next}
        /^- \[ \]/       {item=1; print; next}
        /^- /            {item=0; next}
        item && /^[[:space:]>]/ {print}
    ' "$inbox" 2>/dev/null | while IFS= read -r line; do
        if [[ "$line" =~ ^-\ \[\ \].*\[([0-9]{4}-[0-9]{2}-[0-9]{2})[]\ ] ]]; then
            d_epoch=$(date -d "${BASH_REMATCH[1]}" +%s 2>/dev/null || echo "")
            if [[ -n "$d_epoch" ]]; then
                age_days=$(( (now_epoch - d_epoch) / 86400 ))
                [[ "$age_days" -ge 2 ]] && line="$line ⏳(lying ${age_days} d)"
            fi
        fi
        printf '%s\n' "$line"
    done || true)
    if [[ -n "$unproc" ]]; then
        unproc_n=$(printf '%s\n' "$unproc" | grep -c '^- \[ \]' || true)
        echo "[watchman] 📥 inbox: $unproc_n unprocessed in \"New\" ($inbox) — do them or move to \"Processed\":"
        echo ""
        printf '%s\n' "$unproc"
    fi

    # structure validator: a broken item WITHOUT the `- [ ]` marker doesn't exist for the mechanisms (not pinged, not
    # counted). A line in "New" that is not an item / a continuation / a header is a suspect lost heading -> shout.
    broken=$(awk -v NEWH="$newh" '
        $0 == NEWH {sect=1; next}
        /^## /           {sect=0}
        !sect            {next}
        /^$/ || /^[[:space:]]/ || /^>/ || /^- \[/ || /^_\(порожньо\)_$/ || /^_\(empty\)_$/ {next}
        {print NR": "substr($0,1,90)}
    ' "$inbox" 2>/dev/null || true)
    if [[ -n "$broken" ]]; then
        echo "[watchman] 🔴 inbox STRUCTURE SUSPICIOUS ($inbox) — lines in \"New\" without a \`- [ ]\` marker and without indentation (maybe a lost item heading; such an item is INVISIBLE to pings). Check and fix:"
        printf '%s\n' "$broken" | head -5 | u8
    fi
fi

# ── 5. CODER MODE: .watchlist (shared files). Switched on by the PRESENCE of the file — no hard-coded names.
# Never dumps a file — only a truncated delta.

watchlist="$agent_dir/.watchlist"

if [[ -f "$watchlist" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%%#*}"                                  # strip the comment
        line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        [[ -z "$line" ]] && continue

        if [[ "$line" = /* ]]; then wf="$line"; else wf="$WORKSPACE/$line"; fi
        [[ -f "$wf" ]] || continue

        key=$(echo -n "$wf" | sha256sum | cut -c1-8)
        snap="$MARKER_DIR/${session_id}-wl-${key}.snap"

        cur_hash=$(sha256sum "$wf" | awk '{print $1}')
        prev_hash=""
        [[ -f "$snap" ]] && prev_hash=$(sha256sum "$snap" | awk '{print $1}')
        [[ "$cur_hash" == "$prev_hash" ]] && continue

        if [[ -z "$prev_hash" ]]; then
            # First sight: do NOT dump — only record the base for future deltas.
            echo "[watchman] 👁 Watching a shared file: $line ($(wc -l < "$wf") lines). Read it yourself if needed — from now on I show only changes."
        else
            echo "[watchman] ⚠ A shared file CHANGED: $line — another agent wrote to it (maybe to you). Delta:"
            echo ""
            { diff -u "$snap" "$wf" 2>/dev/null || true; } \
                | tail -n +3 \
                | grep -E '^[+-]' \
                | head -40 | u8 || true
            echo ""
            echo "(<=40 lines of delta; read the whole file yourself if it concerns you)"
        fi
        cp "$wf" "$snap" 2>/dev/null || true
    done < "$watchlist"
fi

exit 0
