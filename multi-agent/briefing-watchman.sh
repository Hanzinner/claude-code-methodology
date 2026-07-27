#!/usr/bin/env bash
# UserPromptSubmit hook — inject a fresh briefing.md AND inbox.md when they change.
# Also bootstraps a missing inbox.md + two TODO files from templates.
#
# See docs/multi-agent.md (delivery layer) and docs/context-management.md.
#
# On every user prompt in an agent session (once the session is tied to an agent):
#
#   1. BOOTSTRAP (creates only, never overwrites):
#      - <agent>/inbox.md                    — cross-agent inbox
#      - <agent>/<name>-shared-TODO.md       — shared with the operator
#      - <agent>/<name>-agent-TODO.md        — the agent's own open-loops
#
#   2. WATCH briefing.md -> marker <sid>-briefing.hash
#   3. WATCH inbox.md    -> ping only the unprocessed items (never a full dump)
#   4. CODER MODE .watchlist -> show only the delta of shared repo files
#
# Silent if the session isn't an agent, or nothing changed. Fails open (exit 0).
#
# Config (env):
#   CLAUDE_PROJECTS_ROOT  workspace root            (default: $HOME/claude-projects)
#   CLAUDE_AGENTS_ROOT    dir holding agent folders (default: <projects>/Agents)

set -euo pipefail
export LC_ALL=C.UTF-8   # so ${s,,} lowercases non-ASCII (e.g. Cyrillic aliases) regardless of env

PROJECTS="${CLAUDE_PROJECTS_ROOT:-$HOME/claude-projects}"
AGENTS_ROOT="${CLAUDE_AGENTS_ROOT:-$PROJECTS/Agents}"
MARKER_DIR="$HOME/.claude/briefing-watchman"
IDENTITY_DIR="$HOME/.claude/agent-identity"
mkdir -p "$MARKER_DIR" "$IDENTITY_DIR"

input=$(cat)
session_id=$(echo "$input" | grep -oP '"session_id"\s*:\s*"\K[^"]+' | head -1)
cwd=$(echo "$input" | grep -oP '"cwd"\s*:\s*"\K[^"]+' | head -1)
[[ -z "$session_id" || -z "$cwd" ]] && exit 0

identity_file="$IDENTITY_DIR/$session_id"

# --- AGENT IDENTITY ----------------------------------------------------------
#
# The obvious gate `[[ -f $cwd/briefing.md ]] || exit 0` was wrong: the operator
# never starts sessions from an agent's folder — cwd is always the workspace root.
# That gate killed the hook in 100% of real sessions (it never fired once for a
# month). So resolve identity three ways instead:
#
#   1. cwd contains briefing.md               -> cwd mode (original behaviour)
#   2. ~/.claude/agent-identity/<sid> exists  -> use the recorded folder
#   3. otherwise a NARROW match of the prompt to Agents/*/ (and Agents/*/*/) that
#      have briefing.md: the prompt must essentially BE the name (<=40 chars).
#      Normalize (lowercase, strip spaces/_/-, drop trailing "agent" and "vN").
#      Exactly one match -> record identity. Zero or many -> exit quietly, so a
#      mid-work mention of another agent doesn't hijack the session.

norm_name() {
    local s prev
    s="${1,,}"                      # NOT tr: tr won't lowercase non-ASCII
    s=$(printf '%s' "$s" | tr -d ' _-')
    # Strip suffixes in a LOOP — order varies: "foo-agent v2" -> strip v2 then agent.
    # A fixed order (agent, then vN) mismatched real names used for new generations.
    prev=""
    while [[ "$s" != "$prev" ]]; do
        prev="$s"
        s=$(printf '%s' "$s" | sed -E 's/v[0-9]+$//')
        s="${s%agent}"
    done
    printf '%s' "$s"
}

agent_dir=""
if [[ -f "$cwd/briefing.md" ]]; then
    agent_dir="$cwd"
elif [[ -f "$identity_file" ]]; then
    agent_dir=$(cat "$identity_file" 2>/dev/null || true)
    [[ -n "$agent_dir" && -f "$agent_dir/briefing.md" ]] || agent_dir=""
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
                hit=0
                [[ "$(norm_name "$(basename "$d")")" == "$want" ]] && hit=1
                # .aliases: one human-language alias per line (any script), same
                # normalization; >1 match across agents -> silence (handled below)
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
shared_todo="$agent_dir/${agent_name}-shared-TODO.md"
agent_todo="$agent_dir/${agent_name}-agent-TODO.md"

# --- BOOTSTRAP: inbox ---
if [[ ! -f "$inbox" ]]; then
    cat > "$inbox" <<EOF
# $agent_name — inbox

> Incoming from outside: other agents / the operator / reminders.
> Got an item -> handle it -> **move it to \`## Processed\`** with a date.
> Keep \`## New\` thin — it lands in context on every change.

## New

_(empty)_

## Processed

_(moved here — with a date)_
EOF
fi

# --- BOOTSTRAP: shared TODO (shared with the operator) ---
if [[ ! -f "$shared_todo" ]]; then
    cat > "$shared_todo" <<EOF
# $agent_name — shared TODO

> Tasks held jointly with the operator: waiting on their decision/action,
> or explicitly asked to record.

## Active

_(empty)_

## Closed

_(moved here — with a date)_
EOF
fi

# --- BOOTSTRAP: agent TODO (own open-loops) ---
if [[ ! -f "$agent_todo" ]]; then
    cat > "$agent_todo" <<EOF
# $agent_name — own TODO (open-loops)

> The agent's unfinished work — things started/promised but not done.
> When the operator returns after a pause, surface what's hanging.

## Open loops

_(empty)_

## Closed

_(moved here — with a date)_
EOF
fi

# --- Helper: check-and-inject one watched file ---
# Args: <file-path> <marker-suffix> <header-line>
check_and_inject() {
    local file="$1" suffix="$2" header="$3"
    local marker="$MARKER_DIR/${session_id}-${suffix}.hash"
    local current_hash prev_hash=""

    [[ -f "$file" ]] || return 0
    current_hash=$(sha256sum "$file" | awk '{print $1}')
    [[ -f "$marker" ]] && prev_hash=$(cat "$marker" 2>/dev/null || true)

    # Legacy compat: v1 used <sid>.hash (no suffix). Adopt it as the briefing
    # marker so migrating sessions don't re-inject after an upgrade.
    if [[ -z "$prev_hash" && "$suffix" == "briefing" ]]; then
        local legacy="$MARKER_DIR/${session_id}.hash"
        if [[ -f "$legacy" ]]; then
            prev_hash=$(cat "$legacy" 2>/dev/null || true)
            mv "$legacy" "$marker" 2>/dev/null || true
        fi
    fi

    [[ "$current_hash" == "$prev_hash" ]] && return 0

    {
        if [[ -z "$prev_hash" ]]; then
            echo "[watchman] $header — first shown this session:"
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

# --- INBOX: persistent reminder, never a full dump --------------------------
#
# The hook never cat's the whole inbox (briefing is the exception): `## Processed`
# only grows. Instead, while `- [ ]` items hang in `## New`, inject ONLY those
# items (with their continuation lines) on EVERY prompt until they're moved to
# `## Processed`. An inbox is a to-do, not a doorbell: a one-shot inject on hash
# change lost items filed long ago or by another session. Empty -> silence.

if [[ -f "$inbox" ]]; then
    # Item age: delivery now reliably spreads stale content too, so an item that
    # has sat >=2 days gets a "(N days old)" marker — not a block, a suspicion
    # flag so the agent re-checks currency before acting. Unparseable date -> skip.
    now_epoch=$(date +%s)
    unproc=$(awk '
        /^## New/     {sect=1; next}
        /^## /        {sect=0}
        !sect         {next}
        /^- \[ \]/    {item=1; print; next}
        /^- /         {item=0; next}
        item && /^[[:space:]>]/ {print}
    ' "$inbox" 2>/dev/null | while IFS= read -r line; do
        if [[ "$line" =~ ^-\ \[\ \].*\[([0-9]{4}-[0-9]{2}-[0-9]{2})\] ]]; then
            d_epoch=$(date -d "${BASH_REMATCH[1]}" +%s 2>/dev/null || echo "")
            if [[ -n "$d_epoch" ]]; then
                age_days=$(( (now_epoch - d_epoch) / 86400 ))
                [[ "$age_days" -ge 2 ]] && line="$line ⏳(${age_days} days old)"
            fi
        fi
        printf '%s\n' "$line"
    done || true)
    if [[ -n "$unproc" ]]; then
        unproc_n=$(printf '%s\n' "$unproc" | grep -c '^- \[ \]' || true)
        echo "[watchman] 📥 inbox: $unproc_n unprocessed in New ($inbox) — do it or move it to Processed:"
        echo ""
        printf '%s\n' "$unproc"
    fi

    # Structure validator: a malformed item WITHOUT a `- [ ]` marker does not
    # exist for the mechanism (never pinged, never counted) — that silently lost
    # real tasks. A line in `## New` that isn't an item/continuation/header is a
    # suspected lost heading -> shout.
    broken=$(awk '
        /^## New/  {sect=1; next}
        /^## /     {sect=0}
        !sect      {next}
        /^$/ || /^[[:space:]]/ || /^>/ || /^- \[/ || /^_\(empty\)_$/ {next}
        {print NR": "substr($0,1,90)}
    ' "$inbox" 2>/dev/null || true)
    if [[ -n "$broken" ]]; then
        echo "[watchman] 🔴 inbox STRUCTURE SUSPECT ($inbox) — lines in New without a \`- [ ]\` marker and without indentation (possibly a lost item heading; such an item is INVISIBLE to pings). Check and fix:"
        printf '%s\n' "$broken" | head -5
    fi
fi

# --- CODER MODE: .watchlist (shared project files) --------------------------
#
# Enabled by the mere presence of a `.watchlist` file in the agent's folder.
# Format: one path per line (relative to the workspace root, or absolute); # = comment.
#
# Why: coder agents talk through SHARED repo files (a backlog, shared notes) and
# COMMIT them. The addressee never learns he was written to until the human nudges.
#
# Why a snapshot, not `git diff HEAD`: changes ARRIVE COMMITTED (another agent
# already committed) -> a diff against HEAD is empty. A snapshot at last-shown
# gives an honest delta regardless of git. Never dumps the file — only the delta.

watchlist="$agent_dir/.watchlist"
if [[ -f "$watchlist" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%%#*}"                                  # strip comment
        line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        [[ -z "$line" ]] && continue

        if [[ "$line" = /* ]]; then wf="$line"; else wf="$PROJECTS/$line"; fi
        [[ -f "$wf" ]] || continue

        key=$(echo -n "$wf" | sha256sum | cut -c1-8)
        snap="$MARKER_DIR/${session_id}-wl-${key}.snap"

        cur_hash=$(sha256sum "$wf" | awk '{print $1}')
        prev_hash=""
        [[ -f "$snap" ]] && prev_hash=$(sha256sum "$snap" | awk '{print $1}')
        [[ "$cur_hash" == "$prev_hash" ]] && continue

        if [[ -z "$prev_hash" ]]; then
            # First sight: don't dump — just record the baseline for future deltas.
            echo "[watchman] 👁 Watching shared file: $line ($(wc -l < "$wf") lines). Read it yourself if relevant — from now I'll show only changes."
        else
            echo "[watchman] ⚠ CHANGED shared file: $line — another agent appended (maybe to you). Delta:"
            echo ""
            { diff -u "$snap" "$wf" 2>/dev/null || true; } \
                | tail -n +3 \
                | grep -E '^[+-]' \
                | head -40 || true
            echo ""
            echo "(<=40 lines of delta; read the full file yourself if it concerns you)"
        fi
        cp "$wf" "$snap" 2>/dev/null || true
    done < "$watchlist"
fi

exit 0
