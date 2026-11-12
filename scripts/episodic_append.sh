#!/usr/bin/env bash
# THE sanctioned way to write to the episodic log ("when did we do X"). Why: two agents once swallowed each other's
# entries by read-modify-writing the whole file, and another tore someone else's heading. Same class of bug the
# inbox append helper solves for inboxes.
# Usage: episodic_append.sh <YYYY-MM> <<'T'
# ## YYYY-MM-DD (agent)
# text...
# T
# Guarantees: flock | APPEND ONLY (other entries are physically never read-and-rewritten) |
# post-validation: the file only grew and the old content is a prefix of the new one.
# Dir: $EPISODIC_DIR (override, for tests) > $CCM_EPISODIC_DIR (settings) > <claude dir>/memory/episodic.
set -euo pipefail
eval "$(python3 "$(dirname "$(readlink -f "$0")")/../lib/ccm_conf.py" --shell)"
EP=${EPISODIC_DIR:-$CCM_EPISODIC_DIR}
month="${1:?month YYYY-MM}"; shift || true
# only YYYY-MM: a full date or an agent name here once created a separate "month" nobody ever read
[[ "$month" =~ ^20[0-9]{2}-(0[1-9]|1[0-2])$ ]] || { echo "episodic_append: the first argument is a month YYYY-MM (e.g. $(date +%Y-%m)), not '$month'; the text goes through stdin" >&2; exit 2; }
text="${*:-}"
[[ -n "$text" ]] || text="$(cat)"
[[ -n "$text" ]] || { echo "episodic_append: empty text" >&2; exit 2; }
mkdir -p "$EP"
f="$EP/$month.md"
[[ -f "$f" ]] || echo "# Episodic $month" > "$f"
exec 9>>"$f.lock"
flock -w 15 9 || { echo "episodic_append: could not get the lock" >&2; exit 3; }
before_sz=$(stat -c%s "$f")
before_sha=$(head -c "$before_sz" "$f" | sha256sum | cut -d' ' -f1)
printf '\n%s\n' "$text" >> "$f"
after_prefix_sha=$(head -c "$before_sz" "$f" | sha256sum | cut -d' ' -f1)
if [[ "$before_sha" != "$after_prefix_sha" || $(stat -c%s "$f") -le $before_sz ]]; then
    echo "episodic_append: POST-VALIDATION FAILED: the old content changed or the file did not grow - check $f by hand" >&2
    exit 5
fi
echo "OK: appended to $f (+$(( $(stat -c%s "$f") - before_sz )) bytes, other entries intact)"
