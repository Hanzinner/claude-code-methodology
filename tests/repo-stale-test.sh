#!/usr/bin/env bash
# repo_stale.py: an old dirty file -> one letter; fresh and clean repos -> none; the next day again; hq from the toml.
# RS=<path> tests another copy.
set -u
HERE=$(dirname "$(readlink -f "$0")")
RS=${RS:-$HERE/../scripts/repo_stale.py}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; R="$T/r"; mkdir -p "$T/h"
printf '#!/bin/sh\necho "$1 $(cat)" >> %s/post.log\n' "$T" > "$T/post"; chmod +x "$T/post"; : > "$T/post.log"
mk() { mkdir -p "$R/Project-$1"; ( cd "$R/Project-$1" && /usr/bin/git init -q -b master && /usr/bin/git config user.email t@t && /usr/bin/git config user.name t && echo a > a && /usr/bin/git add -A && /usr/bin/git commit -qm i ); }
run() { HOME="$T/h" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$R" CCM_INBOX_POST="$T/post" CCM_STALE_STATE="$T/st.json" CCM_STALE_LOG="$T/log" CCM_RELEASER_OWNER="$(id -un)" python3 "$RS" > "$T/out" 2>&1; echo $?; }
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; sed 's/^/   /' "$T/out" "$T/post.log"; fi; }
mk Clean; mk Dirty; mk Fresh; mkdir -p "$R/Project-Mono"; echo x > "$R/Project-Mono/x"
echo b > "$R/Project-Dirty/old file ünï.py"; touch -d '2 days ago' "$R/Project-Dirty/old file ünï.py"
echo b > "$R/Project-Fresh/new"
rc=$(run); ok "1 old dirty file -> one letter to the lead, non-ASCII name intact" '[ "$rc" = 0 ] && [ "$(wc -l < "$T/post.log")" = 1 ] && grep -q "^Dirty-HQ .*old file ünï.py" "$T/post.log"'
ok "1b clean, fresh and non-repo folders -> no letter" '! grep -qE "^(Clean|Fresh|Mono)-HQ" "$T/post.log"'
rc=$(run); ok "2 same day -> no repeat" '[ "$(wc -l < "$T/post.log")" = 1 ]'
python3 -c "import json;json.dump({'Project-Dirty':'2000-01-01'},open('$T/st.json','w'))"; rc=$(run); ok "3 next day -> a letter again" '[ "$(wc -l < "$T/post.log")" = 2 ]'
printf 'hq = "Other-HQ"\n' > "$R/Project-Dirty/release.toml"; touch -d '2 days ago' "$R/Project-Dirty/release.toml"; rm "$T/st.json"; rc=$(run); ok "4 hq from release.toml" 'grep -q "^Other-HQ " "$T/post.log"'
echo "repo-stale: $pass pass, $fail fail"; [ $fail = 0 ]
