#!/usr/bin/env bash
# mistakes_review.sh + mistakes_review_catchup.sh. MR=<path> tests another copy of the review.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" HANZ_TEST=1 CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T/ws" CCM_AGENTS_DIR="$T/Agents"; mkdir -p "$HOME" "$T/ws"
printf "#!/bin/sh\necho \"\$1|\${2:-\$(cat)}\" >> %s/letters\n" "$T" > "$T/post"; chmod +x "$T/post"; : > "$T/letters"; export CCM_INBOX_POST="$T/post"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | sed "s/^/   /"; fi; }
MR=${MR:-$HERE/../scripts/mistakes_review.sh}; MC=${MC:-$HERE/../scripts/mistakes_review_catchup.sh}
M="$T/M.md"
cat > "$M" <<'EOT'
# MISTAKES
## 2026-01-02 · Agent-A · first thing [class 1]
**What happened:** x
**Status:** OPEN
## 2026-01-03 · Agent-B · second thing
**Status:** MECHANIZED (Was: OPEN)
## 2026-01-04 · Agent-C · third thing
**Статус:** OPEN
## [2026-01-05] old format
**Status:** ACCEPTED
EOT
export MISTAKES_OVERRIDE="$M"
out=$(CCM_MISTAKES_KEEPER=Keeper bash "$MR" 2>&1)
ok "1 two OPEN (one Ukrainian status word) -> one letter, count 2" '[ "$(grep -c "^Keeper|" "$T/letters")" = 1 ] && grep -q "2 open" "$T/letters"'
ok "1b the letter lists the OPEN headings, not the closed ones" 'grep -q "first thing" "$T/letters" && grep -q "third thing" "$T/letters" && ! grep -q "second thing" "$T/letters"'
ok "1c log line has the supervisor prefix" 'echo "$out" | grep -q "mistakes-review: 2 OPEN"'
: > "$T/letters"; out=$(bash "$MR" 2>&1)
ok "2 keeper empty -> no letter, the log line says so" '[ ! -s "$T/letters" ] && echo "$out" | grep -q "mistakes-review: 2 OPEN (no keeper"'
sed -i 's/^\*\*Status:\*\* OPEN$/**Status:** MECHANIZED/; s/^\*\*Статус:\*\* OPEN$/**Status:** ACCEPTED/' "$M"; : > "$T/letters"
out=$(CCM_MISTAKES_KEEPER=Keeper bash "$MR" 2>&1)
ok "3 no OPEN -> full silence" '[ -z "$out" ] && [ ! -s "$T/letters" ]'
out=$(MISTAKES_OVERRIDE="$T/none.md" bash "$MR" 2>&1)
ok "4 no journal -> silence, rc 0" '[ -z "$out" ]'
# catch-up
LOGF="$T/rev.log"; export MISTAKES_REVIEW_LOG="$LOGF"; printf '#!/bin/sh\necho ran >> %s/ran\n' "$T" > "$T/rev"; chmod +x "$T/rev"; export MISTAKES_REVIEW="$T/rev"
bash "$MC"; ok "5 no log yet -> catch-up runs" '[ -f "$T/ran" ] && grep -q CATCHUP "$LOGF"'
rm -f "$T/ran"; touch "$LOGF"; bash "$MC"; ok "6 fresh log -> catch-up stays silent" '[ ! -f "$T/ran" ]'
touch -d '8 days ago' "$LOGF"; bash "$MC"; ok "7 log older than 7 days -> catch-up runs" '[ -f "$T/ran" ]'
echo "mistakes-review: $pass pass, $fail fail"; [ $fail = 0 ]
