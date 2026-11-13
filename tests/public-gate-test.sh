#!/usr/bin/env bash
# public_gate.sh + public_gate_selftest.sh. PG=<path> tests another copy of the gate, PS=<path> of the nightly wrapper.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" HANZ_TEST=1 CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T/ws" CCM_AGENTS_DIR="$T/Agents"; mkdir -p "$HOME" "$T/ws"
printf "#!/bin/sh\necho \"\$1|\${2:-\$(cat)}\" >> %s/letters\n" "$T" > "$T/post"; chmod +x "$T/post"; : > "$T/letters"; export CCM_INBOX_POST="$T/post"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | sed "s/^/   /"; fi; }
PG=${PG:-$HERE/../scripts/public_gate.sh}; PS=${PS:-$HERE/../scripts/public_gate_selftest.sh}
out=$(bash "$PG" --selftest 2>&1); rc=$?
ok "1 the built-in matrix passes (5 red cases + 1 green)" '[ $rc = 0 ] && [ "$(echo "$out" | grep -c "  ok ")" = 6 ]'
mkrepo() { d="$T/$1"; mkdir -p "$d"; ( cd "$d"; git init -q .; git config user.email t@t; git config user.name T; for i in 1 2 3 4 5 6; do echo "line $i" > f$i.txt; done; [ -n "${2:-}" ] && printf '%s\n' "$3" > "$2"; git add -A; git commit -qm init ); }
mkrepo clean; out=$(bash "$PG" "$T/clean" 2>&1); rc=$?
ok "2 a clean snapshot -> rc 0 and the verdict" '[ $rc = 0 ] && echo "$out" | grep -q "CLEAN"'
mkrepo cyr x.txt "Привіт"; out=$(bash "$PG" "$T/cyr" 2>&1); rc=$?
ok "3 Cyrillic in a tracked file -> rc 1" '[ $rc = 1 ] && echo "$out" | grep -q "CYRILLIC"'
out=$(CCM_PUBLIC_GATE_CYRILLIC=0 bash "$PG" "$T/cyr" 2>&1); rc=$?
ok "3b Cyrillic check off by the key -> rc 0" '[ $rc = 0 ]'
mkrepo nm n.txt "written by Zorba"; out=$(bash "$PG" "$T/nm" 2>&1); rc=$?
ok "4a names list empty (default) -> the name check is skipped, rc 0" '[ $rc = 0 ]'
out=$(CCM_PUBLIC_GATE_NAMES='Zorba|Acme' bash "$PG" "$T/nm" 2>&1); rc=$?
ok "4b a listed name -> rc 1" '[ $rc = 1 ] && echo "$out" | grep -q "NAMES"'
mkrepo few; ( cd "$T/few" && git rm -q f1.txt f2.txt f3.txt && git commit -qm rm ); out=$(bash "$PG" "$T/few" 2>&1); rc=$?
ok "5 fewer than 5 tracked files -> BROKEN, rc 1 (no false green)" '[ $rc = 1 ] && echo "$out" | grep -q "GATE BROKEN"'
mkdir -p "$T/notrepo"; out=$(bash "$PG" "$T/notrepo" 2>&1); rc=$?
ok "6 not a repo -> BROKEN, rc 1 (empty must not mean clean)" '[ $rc = 1 ]'
out=$(bash "$PG" 2>&1); rc=$?; ok "7 no argument -> usage, rc 2" '[ $rc = 2 ]'
# a gate that cannot fail: break a copy so the Cyrillic check never fires -> its selftest must go red and it must refuse
mkdir -p "$T/sc"; sed 's/\[ "\$cyr_files" -gt 0 \]/false/' "$PG" > "$T/sc/public_gate.sh"; chmod +x "$T/sc/public_gate.sh"; cp -r "$HERE/../lib" "$T/lib"
out=$(bash "$T/sc/public_gate.sh" --selftest 2>&1); rc=$?
ok "8 a gate with the Cyrillic check disabled -> its own selftest goes RED" '[ $rc = 1 ] && echo "$out" | grep -q "BAD cyr"'
out=$(bash "$T/sc/public_gate.sh" "$T/clean" 2>&1); rc=$?
ok "8b ...and it refuses to work (GATE BROKEN) even on a clean snapshot" '[ $rc = 1 ] && echo "$out" | grep -q "GATE BROKEN"'
export LOG="$T/pg.log"
out=$(GATE="$PG" bash "$PS" 2>&1); rc=$?
ok "9 the nightly selftest run -> rc 0, a log line with rc=0" '[ $rc = 0 ] && grep -q " rc=0 " "$LOG"'
out=$(GATE="$PG" bash "$PS" --check 2>&1); rc=$?; ok "9b --check on a fresh green run -> rc 0" '[ $rc = 0 ]'
echo "$(date -d '40 hours ago' '+%F %T') rc=0 x" > "$LOG"; out=$(bash "$PS" --check 2>&1); rc=$?
ok "10 --check on a stale run -> rc 1" '[ $rc = 1 ] && echo "$out" | grep -q stale'
echo "$(date '+%F %T') rc=1 selftest FAIL" > "$LOG"; out=$(bash "$PS" --check 2>&1); rc=$?
ok "11 --check on a red run -> rc 1" '[ $rc != 0 ]'
rm "$LOG"; out=$(bash "$PS" --check 2>&1); rc=$?; ok "12 --check with no log -> rc 3" '[ $rc = 3 ]'
out=$(GATE="$T/sc/public_gate.sh" bash "$PS" 2>&1); rc=$?
ok "13 the nightly run over the broken gate -> rc 1 and the BAD case in the log" '[ $rc = 1 ] && grep -q "BAD cyr" "$LOG"'
echo "public-gate: $pass pass, $fail fail"; [ $fail = 0 ]
