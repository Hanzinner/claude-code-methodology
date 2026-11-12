#!/usr/bin/env bash
# creds: list/path/run against a sandbox store. CR=<path> tests another copy. Values must never be printed.
set -u
HERE=$(dirname "$(readlink -f "$0")")
CR=${CR:-$HERE/../bin/creds}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/h" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_SECRETS_DIR="$T/store" CCM_WORKSPACE="$T/ws"
mkdir -p "$HOME" "$CCM_SECRETS_DIR/search" "$CCM_WORKSPACE"
SECRET="s3cr3tvalue$$"
printf 'SEARCH_KEY=%s\nOTHER=1\n' "$SECRET" > "$CCM_SECRETS_DIR/search/tavily.env"
printf 'TG=abc\n' > "$CCM_SECRETS_DIR/telegram.env"
printf 'TG=old\n' > "$CCM_SECRETS_DIR/telegram.env.bak1"
printf 'X=1\n' > "$CCM_SECRETS_DIR/google-a.env"; printf 'X=2\n' > "$CCM_SECRETS_DIR/google-b.env"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

out=$("$CR" list 2>&1)
ok "1 list shows files and variable NAMES" 'grep -q "tavily.env" <<<"$out" && grep -q "SEARCH_KEY" <<<"$out"'
ok "2 list never prints a value" '! grep -q "$SECRET" <<<"$out"'
ok "3 list hides .bak files" '! grep -q "bak1" <<<"$out"'
p=$("$CR" path TAVILY); ok "4 path resolves a case-insensitive substring" '[ "$p" = "$CCM_SECRETS_DIR/search/tavily.env" ]'
"$CR" path google >/dev/null 2>"$T/err"; rc=$?; ok "5 ambiguous name -> rc 2 with candidates" '[ $rc = 2 ] && grep -q google-a "$T/err" && grep -q google-b "$T/err"'
"$CR" path nothing-here >/dev/null 2>&1; ok "6 unknown name -> rc 2" '[ $? = 2 ]'
r=$("$CR" run tavily -- sh -c 'test "$SEARCH_KEY" = "'"$SECRET"'" && echo present'); ok "7 run exports the variables to the command" '[ "$r" = present ]'
"$CR" run tavily sh >/dev/null 2>&1; ok "8 run without -- -> rc 2" '[ $? = 2 ]'
"$CR" bogus >/dev/null 2>&1; ok "9 unknown action -> rc 2" '[ $? = 2 ]'
"$CR" >/dev/null 2>&1; ok "10 no args -> usage, rc 2" '[ $? = 2 ]'
echo "creds: $pass pass, $fail fail"; [ $fail = 0 ]
