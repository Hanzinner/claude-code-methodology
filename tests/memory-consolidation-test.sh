#!/usr/bin/env bash
# memory_consolidation.sh: the run gate, a failed claude run, a clean run, the md5 read-only alarm. MC=<path> tests another copy.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" HANZ_TEST=1 CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T/ws" CCM_AGENTS_DIR="$T/Agents"; mkdir -p "$HOME" "$T/ws"
printf "#!/bin/sh\necho \"\$1|\${2:-\$(cat)}\" >> %s/letters\n" "$T" > "$T/post"; chmod +x "$T/post"; : > "$T/letters"; export CCM_INBOX_POST="$T/post"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | sed "s/^/   /"; fi; }
MC=${MC:-$HERE/../scripts/memory_consolidation.sh}
export CONSOLIDATION_STAMP="$T/last-run" CONSOLIDATION_TSDIR="$T/ts" CONSOLIDATION_LOG="$T/log" CCM_MEMORY_DIR="$T/mem" CCM_CONSOLIDATION_DIR="$T/out"
mkdir -p "$T/ts" "$T/mem"; echo "# idx" > "$T/mem/MEMORY.md"
prompt_ago() { touch -d "-$1 min" "$T/ts/p"; }
g() { CONSOLIDATION_DRY=1 bash "$MC" 2>&1; }
H=$(date +%H)
date +%F > "$T/last-run"; prompt_ago 300; out=$(g)
ok "1 already ran today -> nothing" '[[ -z "$out" ]]'
date -d yesterday +%F > "$T/last-run"; prompt_ago 50; out=$(g)
ok "2 ran yesterday, quiet 50 min -> RUN (quiet)" '[[ "$out" == "RUN: quiet"* ]]'
prompt_ago 5; out=$(g)
if (( 10#$H >= 23 )); then ok "3 5 min quiet, after 23:00 -> RUN (end of day)" '[[ "$out" == *"end of day"* ]]'
else ok "3 5 min quiet, before 23:00 -> nothing" '[[ -z "$out" ]]'; fi
date -d '3 days ago' +%F > "$T/last-run"; prompt_ago 5; out=$(g)
ok "4 a day was missed, no quiet -> RUN (catch-up)" '[[ "$out" == *"catch-up"* ]]'
rm -f "$T/last-run"; out=$(g)
ok "5 never ran -> RUN (catch-up)" '[[ "$out" == *"catch-up"* ]]'
# failing runner: rc 1, no stamp, the letter says FAILED
printf '#!/bin/sh\nexit 7\n' > "$T/runner"; chmod +x "$T/runner"; rm -f "$T/last-run"
out=$(CCM_CONSOLIDATION_KEEPER=Keeper CONSOLIDATION_RUNNER="$T/runner" bash "$MC" --force 2>&1); rc=$?
ok "6 runner rc 7 -> rc 1, stamp NOT written" '[ $rc = 1 ] && [ ! -f "$T/last-run" ]'
ok "6b the letter says FAILED with the rc" 'grep -q "^Keeper|.*FAILED.*rc=7" "$T/letters"'
# good runner: rc 0, stamp = today, report file, one letter; prompt reaches the runner with read-only tools
printf '#!/bin/sh\necho "$@" > %s/args\necho report\n' "$T" > "$T/runner"; : > "$T/letters"
out=$(CCM_CONSOLIDATION_KEEPER=Keeper CONSOLIDATION_RUNNER="$T/runner" bash "$MC" --force 2>&1); rc=$?
ok "7 runner ok -> rc 0, stamp = today, report written" '[ $rc = 0 ] && [ "$(cat "$T/last-run")" = "$(date +%F)" ] && grep -q "^report" "$T/out/$(date +%F).md"'
ok "7b the runner got read-only tools and the memory dir" 'grep -q -- "--tools Read,Grep,Glob" "$T/args" && grep -q "$T/mem" "$T/args"'
ok "7c one letter, md5 unchanged" '[ "$(grep -c "^Keeper|" "$T/letters")" = 1 ] && grep -q "unchanged" "$T/letters"'
# a runner that WRITES into memory -> loud
printf '#!/bin/sh\necho x >> %s/mem/MEMORY.md\necho report\n' "$T" > "$T/runner"; : > "$T/letters"
out=$(CCM_CONSOLIDATION_KEEPER=Keeper CONSOLIDATION_RUNNER="$T/runner" bash "$MC" --force 2>&1)
ok "8 memory changed during the run -> the letter warns" 'grep -q "CHANGED" "$T/letters" && grep -q "WARNING" "$T/letters"'
# no keeper -> no letter
: > "$T/letters"; out=$(CONSOLIDATION_RUNNER="$T/runner" bash "$MC" --force 2>&1)
ok "9 keeper empty -> no letter" '[ ! -s "$T/letters" ]'
echo "memory-consolidation: $pass pass, $fail fail"; [ $fail = 0 ]
