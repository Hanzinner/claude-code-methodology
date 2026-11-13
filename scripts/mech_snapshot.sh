#!/usr/bin/env bash
# mech_snapshot.sh - version history for the CODE OF THE MECHANISMS (hooks, scripts, lib) in a separate git.
# Why: a pile of ~75 scripts whose whole history was 8 `.bak` files - a diff of "what changed in the guard since
# yesterday" was impossible. Conditions that came out of a review, all kept:
#  (1) the snapshot never contains credentials (secrets live in CCM_SECRETS_DIR, not next to code);
#  (2) a WHITELIST only, never `git add -A`;
#  (3) the repo is OUTSIDE the workspace repo (--git-dir ~/.claude/mech.git, work tree = the installed code dir, files
#      stay where they are) - a second git next to the workspace's own would bypass the gates the workspace repo has;
#  (4) a BLOCKING pre-commit hook with secret-scan, and "0 files = I am broken" (a pattern that matches nothing is
#      reported by name: once the snapshot silently lived 5 days without 80 scripts because a relative-path bug made
#      the "did the file vanish" check always say yes);
#  (5) an auto-commit every 10 minutes, `set -euo pipefail`, an undelivered letter is not lost.
# Nothing is ever deleted from history: a file that vanished from disk is removed from the INDEX only (the deletion
# is history too, the old versions stay in the commits).
#
# Cron:   */10 * * * * ~/.claude/scripts/mech_snapshot.sh
# Settings (CCM_*, or env): MECH_GIT_DIR (default ~/.claude/mech.git) · MECH_WORK_TREE (default CCM_CLAUDE_DIR) ·
#   MECH_LOG (default ~/.claude/mech-snapshot.log) · MECH_WHITELIST (one pattern per line, relative to the work tree;
#   default: scripts/*.sh scripts/*.py hooks/* lib/*.py) · MECH_MIN_FILES (default 10) · CCM_MECH_OWNER (agent that gets
#   a letter when the snapshot breaks or a secret is found; empty = log only) · MECH_POST (letter command, default
#   the installed inbox_post.sh) · MECH_SECRET_SCAN (default <claude dir>/bin/secret-scan, else PATH).
# Exit: 0 ok / nothing changed · 3 broken whitelist (a pattern without files, or too few files) · 4 refused pattern.
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
eval "$(python3 "$HERE/../lib/ccm_conf.py" --shell 2>/dev/null)" || true
CLAUDE_DIR="${CCM_CLAUDE_DIR:-$HERE/..}"
GD="${MECH_GIT_DIR:-$HOME/.claude/mech.git}"
WT="${MECH_WORK_TREE:-$CLAUDE_DIR}"; WT="${WT%/}"
LOG="${MECH_LOG:-$HOME/.claude/mech-snapshot.log}"
OWNER="${MECH_OWNER:-${CCM_MECH_OWNER:-}}"
POST="${MECH_POST:-$HERE/inbox_post.sh}"
WS="${CCM_WORKSPACE:-$HOME/claude-projects}"; WS="${WS%/}"
MIN_FILES="${MECH_MIN_FILES:-10}"
SCAN="${MECH_SECRET_SCAN:-}"
[[ -n "$SCAN" ]] || { [[ -x "$CLAUDE_DIR/bin/secret-scan" ]] && SCAN="$CLAUDE_DIR/bin/secret-scan" || SCAN="$(command -v secret-scan || true)"; }
WHITELIST=("scripts/*.sh" "scripts/*.py" "hooks/*" "lib/*.py")
[[ -n "${MECH_WHITELIST:-}" ]] && mapfile -t WHITELIST <<< "$MECH_WHITELIST"
mkdir -p "$(dirname "$LOG")"
log() { echo "$(date -Iseconds) $*" >> "$LOG"; }
# a letter to the owner (if there is one); never fails the script
tell() { [[ -n "$OWNER" ]] || return 0; "$POST" "$OWNER" "$1" >/dev/null 2>&1 || return 1; }
trap 'log "FAIL rc=$? line $LINENO: $BASH_COMMAND"; tell "mech_snapshot failed (line $LINENO) - log $LOG" || true' ERR
# -C "$WT": every git call runs from the work-tree root. Without it `git ls-files` from a cron cwd printed paths
# relative to the cwd, the "did the file vanish" check never found them and removed every script from the index.
g() { /usr/bin/env git -C "$WT" --git-dir="$GD" --work-tree="$WT" "$@"; }
# one letter per cause per day (the job runs every 10 minutes)
alert() {
    local key; key="$(dirname "$LOG")/.mech-alert-$(printf '%s' "$1" | md5sum | cut -c1-8)-$(date +%F)"
    [[ -e "$key" ]] && return 0
    tell "$1" && : > "$key" || true
}

if [[ -z "$SCAN" ]]; then
    log "BROKEN: no secret-scan found - refusing to snapshot code without a secret scanner"
    alert "mech_snapshot: secret-scan not found - the snapshot is switched off until it is installed."
    exit 3
fi
if [[ ! -d "$GD" ]]; then
    /usr/bin/env git init -q --bare "$GD"
    /usr/bin/env git --git-dir="$GD" config core.bare false
    /usr/bin/env git --git-dir="$GD" config user.name "mech-snapshot"
    /usr/bin/env git --git-dir="$GD" config user.email "mech-snapshot@localhost"
    /usr/bin/env git --git-dir="$GD" config status.showUntrackedFiles no
    mkdir -p "$GD/hooks"
    cat > "$GD/hooks/pre-commit" <<HOOK
#!/usr/bin/env bash
# blocking: a secret in the added lines -> the commit is rejected
out=\$(git diff --cached -U0 --no-color | "$SCAN" --diff 2>&1); rc=\$?
if [[ \$rc == 1 ]]; then echo "pre-commit: SECRET - commit rejected: \$out" >&2; exit 1; fi
exit 0
HOOK
    chmod 755 "$GD/hooks/pre-commit"
    log "INIT $GD"
fi

# No pattern or file may point into the workspace: it has its own repo with its own history and gates; duplicating it
# here is a way around those gates.
for pat in "${WHITELIST[@]}"; do
    case "/$pat" in
        "$WS"/*|"${WS}-wt"/*)
            log "REFUSE: whitelist pattern under the workspace: $pat"
            tell "mech_snapshot: a whitelist pattern points into the workspace ($pat) - refusing (a duplicate of the main repo that bypasses its gates). Remove the pattern." || true
            exit 4 ;;
    esac
done
shopt -s nullglob
files=(); empty=()
for pat in "${WHITELIST[@]}"; do
    n0=${#files[@]}
    for f in "$WT"/$pat; do
        [[ -f "$f" && ! -L "$f" ]] || continue
        case "$(readlink -f -- "$f")" in "$WS"/*) log "REFUSE: $f resolves into the workspace - skipped"; continue ;; esac
        files+=("${f#$WT/}")
    done
    (( ${#files[@]} == n0 )) && empty+=("$pat")
done
shopt -u nullglob
# granularity is the PATTERN, not the sum: 12 files >= 10 once looked "fine" while 4 patterns gave zero
if (( ${#empty[@]} )); then
    log "BROKEN: patterns without files: ${empty[*]}"
    alert "mech_snapshot: whitelist pattern(s) matched 0 files - ${empty[*]}. History of those files is not written: fix the path or remove the pattern."
    exit 3
fi
# guard against a false green: a whitelist that gives (almost) nothing means the instrument is broken, not "nothing changed"
if [[ ${#files[@]} -lt $MIN_FILES ]]; then
    log "BROKEN: whitelist gave ${#files[@]} files (<$MIN_FILES)"
    alert "mech_snapshot: whitelist gave ${#files[@]} files - the instrument is broken, mechanism history is not written."
    exit 3
fi
g add -- "${files[@]}"
# files that vanished from disk leave the index (a deletion is history too)
while IFS= read -r gone; do [[ -e "$WT/$gone" ]] || g rm -q --cached -- "$gone"; done < <(g ls-files)
# post-condition (the one that would have caught the bug above): EVERYTHING on the list must be in the index
in_idx=$(g ls-files | wc -l)
if (( in_idx < ${#files[@]} )); then
    log "BROKEN: index has $in_idx files, whitelist gave ${#files[@]}"
    alert "mech_snapshot: the index has $in_idx files, the whitelist gave ${#files[@]} - part of the mechanism code is NOT reaching history."
    exit 3
fi

g diff --cached --quiet && { log "no changes"; exit 0; }
src=0; hits=$(g diff --cached -U0 --no-color | "$SCAN" --diff 2>/dev/null) || src=$?
if [[ $src == 1 && -n "$hits" ]]; then
    while IFS= read -r f; do
        [[ -n "$f" ]] || continue
        # before the first commit there is no HEAD to reset to -> drop from the index with rm --cached
        if g rev-parse -q --verify HEAD >/dev/null; then g reset -q -- "$f" || true; else g rm -q --cached -- "$f" || true; fi
        log "SECRET: \"$f\" taken out of the commit"
        tell "mech_snapshot: SECRET in \"$WT/$f\" ($(printf '%s\n' "$hits" | grep -F -- "$f:" | awk -F: '{print $NF}' | sort -u | tr '\n' ' ')) - not committed; move the secret out of the code into the secrets dir. The value was not printed." \
            || log "WARN: letter not delivered"
    done < <(printf '%s\n' "$hits" | awk -F: '{NF-=2; print}' OFS=: | sort -u)
fi
g diff --cached --quiet && { log "only secrets - nothing to commit"; exit 0; }
n=$(g diff --cached --name-only | wc -l)
g commit -q -m "mech: snapshot $(date '+%F %H:%M') ($n files)"
log "commit OK ($n)"
