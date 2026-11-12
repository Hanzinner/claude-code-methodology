#!/usr/bin/env bash
# inbox_post.sh / inbox_done.sh / inbox_resolve.sh. Runs the repo copy; P=<path to inbox_post.sh> tests another one,
# D=<path to inbox_done.sh>. Sandbox only: HOME, the agents dir and every file are temp; no network.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
P=${P:-$HERE/../scripts/inbox_post.sh}
D=${D:-$HERE/../scripts/inbox_done.sh}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home"; mkdir -p "$HOME/.claude"
export CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T/ws" CCM_AGENTS_DIR="$T/Agents" HANZ_TEST=1
unset INBOX_AGENTS_ROOT
LOG="$HOME/.claude/inbox-post-repairs.log"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "---"; cat "${f:-/dev/null}"; echo "---"; fi; }
cnt() { grep -cF -- "$1" "$f"; }
new() { awk '$0=="## New"{s=1;next} /^## /{s=0} s' "$f"; }

# 1. an empty file: exactly one copy, no pending queue, no duplicate header
f="$T/a/x.md"; mkdir -p "$T/a"; : > "$f"
"$P" "$f" "test empty" 2>/dev/null
ok "1 empty: exactly one copy" '[ "$(cnt "test empty")" = 1 ]'
ok "1b the item is in New" 'new | grep -qF "test empty"'
ok "1c no pending queue" '[ ! -d "$T/a/inbox-pending" ]'
ok "1d one \"## New\" header" '[ "$(grep -c "^## New$" "$f")" = 1 ]'
"$P" "$f" "test empty" >/dev/null 2>&1
ok "2 the same again - idempotent" '[ "$(cnt "test empty")" = 1 ]'
"$P" "$f" "second letter" 2>/dev/null
ok "3 a second letter goes to the same section" '[ "$(grep -c "^## New$" "$f")" = 1 ] && new | grep -qF "second letter"'

# 4. a damaged inbox: only "## Processed"
f="$T/b/x.md"; mkdir -p "$T/b"; printf '# B - inbox\n\n## Processed\n- [x] old\n' > "$f"
err=$("$P" "$f" "letter into damaged" 2>&1 >/dev/null)
ok "4 one copy" '[ "$(cnt "letter into damaged")" = 1 ]'
ok "4b in New, not in Processed" 'new | grep -qF "letter into damaged"'
ok "4c loud on stderr" 'echo "$err" | grep -q "section created at the end"'
ok "4d the old stays" 'grep -qF "[x] old" "$f"'
ok "4e the warning is OUTSIDE New" '! new | grep -q "⚠ inbox_post"'

# 5. a healthy inbox: insert right after the header, the placeholder goes
f="$T/c/x.md"; mkdir -p "$T/c"; printf '# C - inbox\n\n## New\n\n_(empty)_\n\n## Processed\n' > "$f"
"$P" "$f" "healthy" >/dev/null 2>&1
ok "5 one copy" '[ "$(cnt "healthy")" = 1 ]'
ok "5b placeholder removed" '! grep -q "_(empty)_" "$f"'
ok "5c no warning" '! grep -q "⚠ inbox_post" "$f"'
ok "5d the line right after the header" '[ "$(grep -A2 "^## New$" "$f" | sed -n 3p | grep -c healthy)" = 1 ]'
ok "5e the date was added" 'grep -qE "^- \[ \] \[[0-9]{4}-[0-9]{2}-[0-9]{2}\] healthy" "$f"'

# 6. "## New candidates" is a separate section: not touched
f="$T/d/x.md"; mkdir -p "$T/d"; printf '# D\n\n## New candidates\n\n## Processed\n' > "$f"
"$P" "$f" "candidate" >/dev/null 2>&1
ok "6 goes into its own section, no \"## New\" created" '[ "$(grep -c "^## New$" "$f")" = 0 ] && grep -A2 "^## New candidates$" "$f" | grep -q candidate'

# 6b. Ukrainian section names are understood (an inbox from an older swarm)
f="$T/u/x.md"; mkdir -p "$T/u"; printf '# U\n\n## Нові\n\n_(порожньо)_\n\n## Оброблено\n' > "$f"
"$P" "$f" "ua-style" >/dev/null 2>&1
ok "6b \"## Нові\" gets the item, no \"## New\" created, placeholder gone" 'awk "\$0==\"## Нові\"{s=1;next} /^## /{s=0} s" "$f" | grep -qF ua-style && ! grep -q "^## New$" "$f" && ! grep -q "порожньо" "$f"'

# 7. no repair insert in the log so far (no scenario above is a repair one)
ok "7 no repair inserts" '[ ! -s "$LOG" ]'
# 8. the repair path: the log is valid UTF-8 even when a non-ASCII line is cut
f="$T/e/x.md"; mkdir -p "$T/e"; printf '# E\n\n## New\n\n## Processed\n' > "$f"
( source <(sed -n '/^in_new()/p;/^deliver()/,/^}/p;/^insert_into()/,/^}/p;/^heal_new()/,/^}/p' "$P"); inbox="$f"; text="- [ ] [2026-09-22] $(printf 'ж%.0s' $(seq 80))"; first_line="$text"; new_hdr='## New'; source "$(dirname "$P")/inbox_lib.sh"; deliver ) >/dev/null 2>&1
ok "8 repair log is valid UTF-8" '[ -s "$LOG" ] && python3 -c "open(\"$LOG\",encoding=\"utf-8\").read()"'

# 9. who is the addressee: <name>-agent, group folders, .aliases, ambiguity
A="$T/Agents"; mkdir -p "$A/Foo" "$A/Group/Bar-agent" "$A/X1" "$A/X2" "$A/Baz"
for d in Foo Group/Bar-agent X1 X2 Baz; do printf '# t\n\n## New\n\n## Processed\n' > "$A/$d/inbox.md"; done
printf 'app\nbarry\n' > "$A/Group/Bar-agent/.aliases"; printf 'dup\n' > "$A/X1/.aliases"; printf 'dup\n' > "$A/X2/.aliases"
printf '# old names\nOldBaz\n' > "$A/Baz/.aliases"
to() { f=""; out=$("$P" "$1" "letter $1" 2>&1); rc=$?; }
to Foo;     ok "9a folder by name" '[ $rc = 0 ] && grep -q "letter Foo" "$A/Foo/inbox.md"'
to Bar;     ok "9b Bar -> Group/Bar-agent (suffix -agent + group folder)" '[ $rc = 0 ] && grep -q "letter Bar" "$A/Group/Bar-agent/inbox.md"'
to BARRY;   ok "9c alias, any case" '[ $rc = 0 ] && grep -q "letter BARRY" "$A/Group/Bar-agent/inbox.md"'
to OldBaz;  ok "9d an old name via .aliases" '[ $rc = 0 ] && grep -q "letter OldBaz" "$A/Baz/inbox.md"'
to dup;     ok "9e an alias in two folders -> exit 2 with a list" '[ $rc = 2 ] && echo "$out" | grep -q X1 && echo "$out" | grep -q X2'
to Nobody;  ok "9f unknown -> exit 2" '[ $rc = 2 ] && echo "$out" | grep -q "no inbox found"'
out=$("$P" 2>&1); rc=$?
ok "9g no arguments -> usage, rc 2" '[ $rc = 2 ] && echo "$out" | grep -q "inbox_post.sh <agent"'

# 10. inbox_done: the same resolver; duplicates do not give a false post-validation
f="$A/Group/Bar-agent/inbox.md"; printf '# t\n\n## New\n\n- [ ] [2026-09-27] Release X failed\n\n- [ ] [2026-09-27] Release X failed\n\n## Processed\n' > "$f"
out=$("$D" Bar "Release X failed" "closed" 2>&1); rc=$?
ok "10a a duplicate: one closed, rc 0" '[ $rc = 0 ] && [ "$(new | grep -c "Release X")" = 1 ]'
out=$("$D" BARRY "Release X failed" "closed" 2>&1); rc=$?
ok "10b the alias in inbox_done -> the second one closed too" '[ $rc = 0 ] && [ "$(new | grep -c "Release X")" = 0 ]'
ok "10c the entry landed on top of Processed" 'awk "/^## Processed/{s=1;next} s" "$f" | grep -qx "closed"'
out=$("$D" Bar "nothing like this" 2>&1); rc=$?
ok "10d no such item -> rc 4" '[ $rc = 4 ]'

# 12. an option instead of text -> rc 2, the file untouched
f="$A/Foo/inbox.md"; m0=$(md5sum < "$f" 2>/dev/null || md5 -q "$f")
out=$("$P" Foo --dry-run "check" 2>&1); rc=$?
ok "12 text \"--dry-run ...\" -> rc 2, file unchanged" '[ $rc = 2 ] && [ "$(md5sum < "$f" 2>/dev/null || md5 -q "$f")" = "$m0" ]'

# 13. a big letter and the "already in New" check without SIGPIPE (a 61 KB letter once gave rc 141 AFTER delivery)
f="$A/Foo/inbox.md"; big=$(head -c 68000 /dev/urandom | base64 | tr -d '\n' | fold -w 76)
out=$("$P" Foo "- [ ] [2026-09-28] BIG-LETTER-$$
$big" 2>&1); rc=$?
ok "13 a ~90 KB letter -> rc 0, exactly one item" '[ $rc = 0 ] && [ "$(grep -c "BIG-LETTER-$$" "$f")" = 1 ]'
ok "13b no repair inserts" '! grep -q "BIG-LETTER-$$" "$LOG" 2>/dev/null'
out=$("$P" Foo '- [ ] [2026-09-28] regex \b\d+ in a letter-'"$$" 2>&1); rc=$?
ok "13c backslashes in the first line -> found, no repair" '[ $rc = 0 ] && [ "$(grep -cF "\\b\\d+ in a letter-$$" "$f")" = 1 ] && ! grep -q "letter-$$" "$LOG" 2>/dev/null'

# 14. a broken UTF-8 byte in a neighbour's letter: inbox_done closes the right one and keeps the broken one byte for byte
f="$A/Foo/inbox.md"; printf '# t\n\n## New\n\n- [ ] [2026-10-23] cut in the mi\xd0\n\n- [ ] [2026-10-23] close-me-%s\n\n## Processed\n' "$$" > "$f"
out=$("$D" Foo "close-me-$$" "ok" 2>&1); rc=$?
ok "14 a broken byte in the neighbour -> closed, rc 0" '[ $rc = 0 ] && ! new | grep -q "close-me-$$"'
ok "14b file not empty, the broken letter kept byte for byte" '[ -s "$f" ] && grep -q "cut in the mi$(printf "\xd0")$" "$f"'
# 15. a substring in two DIFFERENT letters
printf '# t\n\n## New\n\n- [ ] [2026-10-23] HQ: I WITHDRAW the order about worktrees\n\n- [ ] [2026-10-23] HQ: announcing worktrees\n\n## Processed\n' > "$f"; m0=$(md5sum < "$f" 2>/dev/null || md5 -q "$f")
out=$("$D" Foo "worktrees" "ok" 2>&1); rc=$?
ok "15 an ambiguous substring -> rc 7, both listed, file unchanged" '[ $rc = 7 ] && echo "$out" | grep -q WITHDRAW && echo "$out" | grep -q announcing && [ "$(md5sum < "$f" 2>/dev/null || md5 -q "$f")" = "$m0" ]' "$out"
out=$("$D" Foo "announcing worktrees" "ok" 2>&1); rc=$?
ok "15b a more precise substring -> exactly that one closed" '[ $rc = 0 ] && new | grep -q WITHDRAW && ! new | grep -q announcing'

# 16. the addressee does not listen -> a line to the sender; delivery and rc unchanged
mkdir -p "$T/li"; out=$(INBOX_LISTEN=1 LISTEN_IDENT="$T/li" LISTEN_ROOTS="$T/li" LISTEN_WAIT="$T/li" AGENT_TAB_SESSIONS="$T/li" "$P" Foo "- [ ] [2026-10-24] to-the-silent-$$" 2>&1); rc=$?
ok "16 no alarm and no session -> \"⚠ Foo is not listening\", delivered, rc 0" '[ $rc = 0 ] && echo "$out" | grep -q "⚠ Foo is not listening" && grep -q "to-the-silent-$$" "$A/Foo/inbox.md"' "$out"
out=$("$P" Foo "- [ ] [2026-10-24] test-silence-$$" 2>&1)
ok "16b under tests (HANZ_TEST=1) without INBOX_LISTEN - silent" '[ -z "$out" ]' "$out"

# 17. concurrency: 12 parallel writers, nothing lost, nothing doubled
f="$A/Baz/inbox.md"; printf '# t\n\n## New\n\n## Processed\n' > "$f"
for i in $(seq 1 12); do "$P" Baz "par-$i-$$" >/dev/null 2>&1 & done; wait
ok "17 12 parallel posts -> 12 distinct items, structure intact" '[ "$(grep -c "par-[0-9]*-$$" "$f")" = 12 ] && [ "$(grep -c "^## " "$f")" = 2 ]'
echo "inbox-post: $pass pass, $fail fail"; [ $fail = 0 ]
