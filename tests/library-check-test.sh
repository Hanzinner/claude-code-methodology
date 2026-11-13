#!/usr/bin/env bash
# library_check.py on a fake LIBRARY / settings / crontab (touches no real file, sends no letter: --dry).
# LC=<path> tests another copy. Sandbox: temp HOME, CLAUDE_METHODOLOGY_CONF=/nonexistent, LIBCHECK_* point into the temp dir.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
LC=${LC:-$HERE/../scripts/library_check.py}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" HANZ_TEST=1 CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T"; mkdir -p "$HOME"
C() { python3 "$LC" --dry "$@"; }   # a function: the install path may contain spaces and quotes
mkdir -p "$T/s" "$T/docs" "$T/nofresh"
for f in gate.py tagged.py branch.py cronjob.sh; do echo '#' > "$T/s/$f"; done
printf 'DETECTORS=(branch)\n' > "$T/s/stop-dispatch.sh"
touch "$T/docs/A (2026).pdf" "$T/docs/ok.md"
export LIBCHECK_REPO="$T" LIBCHECK_SETTINGS="$T/settings.json" LIBCHECK_CRON_FILE="$T/cron" LIBCHECK_FRESH_DIRS="$T/nofresh"
H="$T/s/hook-safe.sh"
cat > "$T/settings.json" <<EOT
{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"$H python3 $T/s/gate.py"}]}],
 "Stop":[{"hooks":[{"type":"command","command":"$H $T/s/stop-dispatch.sh"}]}],
 "PostToolUse":[{"matcher":"*","hooks":[{"type":"command","command":"$H $T/s/tagged.py"}]}]}}
EOT
printf '*/5 * * * * %s >> %s 2>&1\n30 12 * * 0 find /tmp -mtime +30 -delete\n' "$T/s/cronjob.sh" "$T/s/run.log" > "$T/cron"
lib() { printf '# L\n%s\n' "$1" > "$T/LIBRARY.md"; }
ALL="- I.1 [gate.py]($T/s/gate.py) — g {hook:PreToolUse}
- I.2 [tagged.py]($T/s/tagged.py) — t {hook:PostToolUse}
- I.3 [stop-dispatch.sh]($T/s/stop-dispatch.sh) — d {hook:Stop}
- I.4 [branch.py]($T/s/branch.py) — branch {hook:Stop}
- I.5 [cronjob.sh]($T/s/cronjob.sh) — c {cron}
- V.1 [A (2026).pdf](docs/A%20(2026).pdf) — pdf {doc}
- V.2 [ok](docs/ok.md) — {doc}
- V.3 [site](https://example.com) — {doc}
- I.9 [~~old.py~~](/nonexistent/old.py) — RETIRED {hook:none}"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "$out" | sed 's/^/   /'; fi; }

lib "$ALL"; out=$(C)
ok "1 all matches -> quiet (brackets in a path, %20, URL, retired, dispatcher, >> log, inline cron)" '[[ "$out" =~ ^[0-9-]+\ [0-9:]+\ library_check:\ no\ differences$ ]]'
lib "$ALL
- V.4 [gone](docs/gone.md) — {doc}"; out=$(C)
ok "2 vanished path -> (a)" 'echo "$out" | grep -q "(a).*docs/gone.md"'
lib "$(echo "$ALL" | grep -v 'I.1 ')"; out=$(C)
ok "3 hook without a line -> (b)" 'echo "$out" | grep -q "(b) hook without a LIBRARY line.*gate.py"'
lib "$(echo "$ALL" | grep -v 'I.4 ')"; out=$(C)
ok "4 dispatcher branch without a line -> (b)" 'echo "$out" | grep -q "(b) hook without a LIBRARY line.*branch.py {hook:Stop}"'
lib "$(echo "$ALL" | grep -v 'I.5 ')"; out=$(C)
ok "5 cron job without a line -> (b)" 'echo "$out" | grep -q "(b) cron job without a LIBRARY line.*cronjob.sh"'
ok "5b a >> target is not counted as a script" '! echo "$out" | grep -q "run.log"'
lib "$(echo "$ALL" | sed 's/t {hook:PostToolUse}/t {hook:Stop}/')"; out=$(C)
ok "6 wrong tag -> (c)" 'echo "$out" | grep -q "(c).*tagged.py — tags {hook:Stop}, settings say {hook:PostToolUse}"'
lib "$ALL
- I.7 [ghost.py]($T/s/cronjob.sh) — {hook:Stop}"; out=$(C)
ok "7 hook tag but not subscribed -> (c)" 'echo "$out" | grep -q "(c).*I.7.*not subscribed"'
lib "$ALL
- I.1 [dup.py]($T/s/gate.py) — {doc}"; out=$(C)
ok "7b duplicate number -> (d)" 'echo "$out" | grep -q "(d) number I.1 twice"'
# 8. (e) new within a day without a line -> letter to the AUTHOR (transcript -> identity)
mkdir -p "$T/fresh" "$T/tr/p" "$T/ident"; printf '# S\n' > "$T/SWARM-TOOLS.md"
echo 'x' > "$T/fresh/new_tool.sh"; echo 'y' > "$T/fresh/known_tool.sh"
printf '%s\n' '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Write","input":{"file_path":"'"$T/fresh/new_tool.sh"'","content":"x"}}]}}' > "$T/tr/p/sid-author.jsonl"
echo "$T/Agents/Some-Agent" > "$T/ident/sid-author"
export LIBCHECK_FRESH_DIRS="$T/fresh" LIBCHECK_TRANSCRIPTS="$T/tr/*/*.jsonl" LIBCHECK_IDENTITY="$T/ident"
lib "$ALL
- I.6 [known_tool.sh]($T/fresh/known_tool.sh) — c {tool}"; out=$(C)
ok "8 new file without a line -> (e) with the author and a letter to the author" 'echo "$out" | grep -q "(e).*new_tool.sh (author: Some-Agent)" && echo "$out" | grep -q "^→ Some-Agent:"'
ok "8b a file with a LIBRARY line is not mentioned" '! echo "$out" | grep -q "known_tool"'
# 9. a real (non --dry) run: the keeper gets ONE letter; empty keeper = no letter
printf '#!/bin/sh\necho "$1|$2" >> %s/letters\n' "$T" > "$T/post"; chmod +x "$T/post"; : > "$T/letters"
lib "$(echo "$ALL" | grep -v 'I.1 ')"; export CCM_INBOX_POST="$T/post" LIBCHECK_FRESH_DIRS="$T/nofresh"
out=$(CCM_LIBRARY_KEEPER=Keeper python3 "$LC" 2>&1)
ok "9 keeper set -> exactly one letter to the keeper" '[ "$(grep -c "^Keeper|" "$T/letters")" = 1 ]'
: > "$T/letters"; out=$(CCM_LIBRARY_KEEPER= python3 "$LC" 2>&1)
ok "9b keeper empty -> no letter, the differences are printed" '[ ! -s "$T/letters" ] && echo "$out" | grep -q "gate.py"'
echo "library-check: $pass pass, $fail fail"; [ $fail = 0 ]
