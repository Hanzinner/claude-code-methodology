#!/usr/bin/env bash
# rename-ref: moves a .md and rewrites links in a sandbox git repo. RR=<path> tests another copy.
set -u
HERE=$(dirname "$(readlink -f "$0")")
RR=${RR:-$HERE/../bin/rename-ref}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/h" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T/ws" CCM_CLAUDE_DIR="$T/cl"
export RENAME_REF_REPO="$T/ws" RENAME_REF_EXTERNAL="$T/ext"   # never look at the real /usr/local/bin, cron, ...
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
mkdir -p "$HOME" "$T/ws/docs" "$T/ws/notes" "$T/ext" "$T/cl"
W=$T/ws; cd "$W"; git init -q .
printf '# Alpha\nsee [b](../notes/beta.md) and [[beta]]\n' > docs/alpha.md
printf '# Beta\nlink [a](../docs/alpha.md#top) and bare docs/alpha.md here, not OLD-alpha.md\n' > notes/beta.md
printf 'root: [a](docs/alpha.md) and [[alpha]]\n' > README.md
printf 'other.md.bak mention docs/alpha.md.bak\n' > notes/gamma.md
git add -A; git commit -qm init
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

"$RR" --dry-run docs/alpha.md docs/omega.md >/dev/null 2>&1; rc=$?
ok "1 --dry-run changes nothing" '[ $rc = 0 ] && [ -f docs/alpha.md ] && [ ! -e docs/omega.md ]'
out=$("$RR" docs/alpha.md docs/omega.md 2>&1); rc=$?
ok "2 rename succeeds, rc 0" '[ $rc = 0 ] && [ -f docs/omega.md ] && [ ! -e docs/alpha.md ]'
ok "3 markdown link rewritten, fragment kept" 'grep -q "(../docs/omega.md#top)" notes/beta.md && grep -q "(docs/omega.md)" README.md'
ok "4 [[stem]] rewritten" 'grep -q "\[\[omega\]\]" README.md'
ok "5 bare path mention rewritten, OLD-alpha.md untouched" 'grep -q "bare docs/omega.md here" notes/beta.md && grep -q "OLD-alpha.md" notes/beta.md'
ok "6 alpha.md.bak mention not ours" 'grep -q "docs/alpha.md.bak" notes/gamma.md'
ok "7 git sees a rename (tracked move)" 'git status --porcelain | grep -q "^R"'
# move to another directory: the moved file's own relative links are recomputed
"$RR" docs/omega.md notes/deep/omega.md >/dev/null 2>&1; rc=$?
ok "8 move to another dir: rc 0, links of the moved file recomputed" '[ $rc = 0 ] && grep -q "(../beta.md)" notes/deep/omega.md && grep -q "(notes/deep/omega.md)" README.md'
# external mention blocks the rename
printf '#!/bin/sh\ncat "%s/notes/beta.md"\n' "$W" > "$T/ext/job.sh"
"$RR" notes/beta.md notes/beta2.md >/dev/null 2>"$T/err"; rc=$?
ok "9 external script mentions the old path -> rc 3, nothing moved" '[ $rc = 3 ] && [ -f notes/beta.md ] && grep -q job.sh "$T/err"'
"$RR" --force-external notes/beta.md notes/beta2.md >/dev/null 2>&1
ok "10 --force-external goes ahead" '[ -f notes/beta2.md ]'
"$RR" notes/beta2.md notes/beta3.txt >/dev/null 2>&1; ok "11 non-.md target -> refused (rc 1)" '[ $? = 1 ] && [ -f notes/beta2.md ]'
"$RR" notes/beta2.md README.md >/dev/null 2>&1; ok "12 target exists -> refused" '[ $? = 1 ] && [ -f notes/beta2.md ]'
printf 'x\n' > "$T/outside.md"; "$RR" "$T/outside.md" notes/o.md >/dev/null 2>&1; ok "13 file outside the workspace -> refused" '[ $? = 1 ] && [ -f "$T/outside.md" ]'
echo "rename-ref: $pass pass, $fail fail"; [ $fail = 0 ]
