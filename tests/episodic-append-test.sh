#!/usr/bin/env bash
# episodic_append.sh in a sandbox: the month is YYYY-MM only. EA=<path> tests another copy.
HERE=$(dirname "$(readlink -f "$0")")
EA=${EA:-$HERE/../scripts/episodic_append.sh}
T=$(mktemp -d); H=$(mktemp -d); trap 'rm -rf "$T" "$H"' EXIT
export HOME="$H" CLAUDE_METHODOLOGY_CONF=/nonexistent EPISODIC_DIR="$T"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }
printf '## 2026-11-12 · X\ntext\n' | bash "$EA" 2026-11 >/dev/null 2>&1; ok "1 YYYY-MM -> appended to 2026-11.md" '[ $? = 0 ] && grep -q text "$T/2026-11.md"'
for m in 2026-11-03 Gotten-Dev 2026-13 "2026-09-22…28 · some-agent"; do
  printf 'x\n' | bash "$EA" "$m" >/dev/null 2>&1; rc=$?
  ok "2 «$m» -> rc 2, no file" '[ $rc = 2 ] && [ ! -e "$T/$m.md" ]'
done
ok "3 only 2026-11.md in the directory" '[ "$(ls "$T" | grep -v lock)" = 2026-11.md ]'
# settings route: no EPISODIC_DIR override, CCM_EPISODIC_DIR from the environment. Skipped for a script that does not
# know CCM_EPISODIC_DIR (e.g. the live original): without the override it would write to its real default directory.
if grep -q CCM_EPISODIC_DIR "$EA"; then
  T2=$(mktemp -d); printf 'via settings\n' | env -u EPISODIC_DIR CCM_EPISODIC_DIR="$T2" bash "$EA" 2026-12 >/dev/null 2>&1
  ok "4 CCM_EPISODIC_DIR is honoured when EPISODIC_DIR is unset" 'grep -q "via settings" "$T2/2026-12.md"'; rm -rf "$T2"
else
  echo "skip: 4 (script has no CCM_EPISODIC_DIR support)"
fi
# append-only: a second entry keeps the first one intact
printf 'second\n' | bash "$EA" 2026-11 >/dev/null 2>&1
ok "5 second append keeps the first entry" 'grep -q text "$T/2026-11.md" && grep -q second "$T/2026-11.md"'
echo "episodic-append: $pass pass, $fail fail"; [ $fail = 0 ]
