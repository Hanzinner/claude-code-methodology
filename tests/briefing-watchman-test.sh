#!/usr/bin/env bash
# briefing-watchman: identity by name, bootstrap, briefing re-injection, hanging inbox items, watchlist delta,
# deferred-letter delivery, optional supervisor line; and it must NOT print detector flags (surface-flags.sh's job).
# Runs the repo copy (installed into a sandbox layout); WM=<path> tests another hook file.
# Sandbox: temp HOME/workspace, no config file, CCM_* env into the temp dir; no network.
set -u
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
WM="${WM:-$HERE/../hooks/briefing-watchman.sh}"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/home" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_WORKSPACE="$T/ws" CCM_AGENTS_DIR="$T/ws/Agents" CCM_TRASH_DIR="$T/trash"
unset CCM_SUPERVISOR_HEARTBEAT
mkdir -p "$HOME" "$T/ws/Agents" "$T/inst/hooks" "$T/inst/lib" "$T/inst/scripts"
cp "$WM" "$T/inst/hooks/briefing-watchman.sh"; cp "$HERE/../lib/ccm_conf.py" "$T/inst/lib/"
# stub inbox_post.sh: appends the item under "## New" of the inbox file given as the first argument
cat > "$T/inst/scripts/inbox_post.sh" <<'STUB'
#!/usr/bin/env bash
t=$(cat); python3 - "$1" "$t" <<'PY'
import sys; p, t = sys.argv[1], sys.argv[2]
s = open(p, encoding="utf-8").read().replace("## New\n", "## New\n\n- [ ] " + t.strip() + "\n", 1); open(p, "w", encoding="utf-8").write(s)
PY
STUB
chmod +x "$T/inst/scripts/inbox_post.sh"
A="$T/ws/Agents"
mkdir -p "$A/Helper" "$A/Docs" "$A/Team/Builder-agent" "$A/_example-agent" "$A/Twin1" "$A/Twin2"
for d in Helper Docs Team/Builder-agent _example-agent Twin1 Twin2; do printf '# %s briefing\nline\n' "$d" > "$A/$d/briefing.md"; done
printf 'documentation\nDoc Writer\n' > "$A/Docs/.aliases"; printf 'pair\n' > "$A/Twin1/.aliases"; printf 'pair\n' > "$A/Twin2/.aliases"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }
hook() {  # hook <sid> <prompt> [cwd]
    python3 -c 'import json,sys;print(json.dumps({"session_id":sys.argv[1],"prompt":sys.argv[2],"cwd":sys.argv[3]}))' "$1" "$2" "${3:-$T/ws}" \
        | bash "$T/inst/hooks/briefing-watchman.sh" 2>&1
}
ident() { cat "$HOME/.claude/agent-identity/$1" 2>/dev/null; }

out=$(hook s1 "Helper")
ok "a prompt that is the agent's name -> identity recorded" '[ "$(ident s1)" = "$A/Helper" ]'
ok "the briefing is shown first time" '[[ "$out" == *"first shown"* && "$out" == *"# Helper briefing"* ]]'
ok "bootstrap: inbox.md + agent-TODO.md + human-TODO.md created" '[ -f "$A/Helper/inbox.md" ] && [ -f "$A/Helper/agent-TODO.md" ] && [ -f "$A/Helper/human-TODO.md" ]'
out=$(hook s1 "what is the status of the build please")
ok "next prompt: briefing unchanged, empty inbox -> silent" '[ -z "$out" ]'
echo "new rule" >> "$A/Helper/briefing.md"
out=$(hook s1 "go on")
ok "briefing content changed -> re-injected as updated" '[[ "$out" == *"updated"* && "$out" == *"new rule"* ]]'
touch "$A/Helper/briefing.md"; out=$(hook s1 "go on")
ok "touch without a content change -> silent" '[ -z "$out" ]'

printf '# inbox\n\n## New\n\n- [ ] [%s] fresh task\n  continuation line\n- [ ] [2020-01-01] ancient task\n\n## Processed\n- [ ] [2020-01-01] already handled\n' "$(date +%F)" > "$A/Helper/inbox.md"
out=$(hook s1 "go on")
ok "hanging items listed (2), with their continuation line" '[[ "$out" == *"2 unprocessed"* && "$out" == *"fresh task"* && "$out" == *"continuation line"* ]]'
ok "an item older than 2 days is marked" '[[ "$out" == *"ancient task"*"lying"* ]]'
ok "an item already under Done is not listed" '[[ "$out" != *"already handled"* ]]'
out2=$(hook s1 "go on")
ok "the items are re-shown on EVERY prompt until moved" '[[ "$out2" == *"2 unprocessed"* ]]'
printf '# inbox\n\n## New\n\nStray heading without a marker\n- [ ] ok item\n\n## Processed\n' > "$A/Helper/inbox.md"
out=$(hook s1 "go on")
ok "a malformed line in New -> the structure warning" '[[ "$out" == *"STRUCTURE SUSPICIOUS"* && "$out" == *"Stray heading"* ]]'
printf '# inbox\n\n## New\n\n## Processed\n' > "$A/Helper/inbox.md"

# watchlist: base on first sight, delta on change, silence when unchanged
printf 'shared/NOTES.md  # comment\nmissing/file.md\n' > "$A/Helper/.watchlist"; mkdir -p "$T/ws/shared"; printf 'a\nb\n' > "$T/ws/shared/NOTES.md"
out=$(hook s1 "go on")
ok "watchlist first sight -> only 'Watching' line, no dump" '[[ "$out" == *"Watching a shared file: shared/NOTES.md"* && "$out" != *"+b"* ]]'
out=$(hook s1 "go on"); ok "unchanged shared file -> silent" '[ -z "$out" ]'
printf 'a\nb\nc from another agent\n' > "$T/ws/shared/NOTES.md"
out=$(hook s1 "go on")
ok "changed shared file -> a delta with the new line" '[[ "$out" == *"CHANGED"* && "$out" == *"+c from another agent"* ]]'

# section names via inbox_lib.sh: a Ukrainian-style inbox ("## Нові") is read too
cp "$HERE/../scripts/inbox_lib.sh" "$T/inst/scripts/"
printf '# inbox\n\n## Нові\n\n- [ ] ukr-style item\n\n## Оброблено\n- [ ] closed one\n' > "$A/Helper/inbox.md"
out=$(hook s1 "go on"); ok "inbox with '## Нові' -> item listed, closed section ignored" '[[ "$out" == *"ukr-style item"* && "$out" != *"closed one"* ]]'
printf '# inbox\n\n## New\n\n## Processed\n' > "$A/Helper/inbox.md"

# not an agent session
out=$(hook s2 "please look at why the nightly job fails and tell me which agent owns it")
ok "an ordinary long prompt -> silent, no identity" '[ -z "$out" ] && [ -z "$(ident s2)" ]'
out=$(hook s3 "example"); ok "the template folder _example-agent is not an agent" '[ -z "$out" ] && [ -z "$(ident s3)" ]'
out=$(hook s4 "pair"); ok "an alias shared by two agents (ambiguous) -> silent" '[ -z "$out" ] && [ -z "$(ident s4)" ]'
out=$(hook s5 "Doc Writer"); ok "an alias from .aliases resolves" '[ "$(ident s5)" = "$A/Docs" ]'
out=$(hook s6 "builder agent v2"); ok "suffix normalization: 'builder agent v2' -> Team/Builder-agent" '[ "$(ident s6)" = "$A/Team/Builder-agent" ]'
out=$(hook s7 "" "$A/Docs"); ok "cwd inside an agent folder -> identity from cwd" '[ "$(ident s7)" = "$A/Docs" ]'
mkdir -p "$A/Docs/sub"; out=$(hook s7 "go" "$A/Helper"); ok "identity first: a later cwd in a neighbour's folder doesn't change who I am" '[ "$(ident s7)" = "$A/Docs" ]'
# renamed folder: identity points at a dead folder whose old name is in .aliases of the new one
mkdir -p "$A/Old"; printf '# old\n' > "$A/Old/briefing.md"; hook s8 "Old" >/dev/null
printf 'old\n' >> "$A/Docs/.aliases"; mv "$A/Old" "$T/old-gone"
out=$(hook s8 "go on"); ok "a renamed folder -> identity rewritten via .aliases" '[ "$(ident s8)" = "$A/Docs" ]'

# deferred letters
mkdir -p "$A/Docs/inbox-pending"; printf 'deferred hello\n' > "$A/Docs/inbox-pending/1.md"
out=$(hook s1 "go on")
ok "a deferred letter in another agent's pending dir is delivered and the file moved to trash" '[[ "$out" == *"delivered a deferred letter"* ]] && grep -q "deferred hello" "$A/Docs/inbox.md" && [ ! -f "$A/Docs/inbox-pending/1.md" ] && [ -f "$T/trash/inbox-pending-delivered/1.md" ]'

# detector flags are surface-flags.sh's job, not the watchman's
mkdir -p "$HOME/.claude/pause-guard-flags"; echo "flag text" > "$HOME/.claude/pause-guard-flags/s1"
out=$(hook s1 "go on"); ok "a detector flag file is neither printed nor removed here" '[[ "$out" != *"flag text"* ]] && [ -f "$HOME/.claude/pause-guard-flags/s1" ]'

# supervisor dead-man line
echo $(( $(date +%s) - 7200 )) > "$T/hb"
out=$(CCM_SUPERVISOR_HEARTBEAT="$T/hb" hook s1 "go on"); ok "stale supervisor heartbeat -> one line" '[[ "$out" == *"supervisor"*"silent for"* ]]'
date +%s > "$T/hb"; out=$(CCM_SUPERVISOR_HEARTBEAT="$T/hb" hook s1 "go on"); ok "fresh heartbeat -> silent" '[ -z "$out" ]'
echo $(( $(date +%s) - 7200 )) > "$T/hb"; out=$(hook s1 "go on"); ok "key not set -> off, silent" '[ -z "$out" ]'

# coding standard in .watchlist: the changelog since the confirmed version, not a raw diff
cp "$HERE/../scripts/standard_version.py" "$T/inst/scripts/"
printf '# Standard\n**Version: 2** (test)\n\n## Changelog\n\n- **v2** (2026-11) — NEW RULE TWO\n- **v1** (2026-11) — first\n' > "$T/ws/CODING-STANDARD.md"
mkdir -p "$A/Coder"; printf '# Coder briefing\nStandard: v1 read 2026-11-01\n' > "$A/Coder/briefing.md"; echo "CODING-STANDARD.md" > "$A/Coder/.watchlist"
out=$(hook s9 "Coder")
ok "coder behind the standard (v1 read, v2 out) -> the v2 changelog entry, not a diff" '[[ "$out" == *"NEW RULE TWO"* && "$out" != *"@@"* ]]'
sed -i 's/Standard: v1 read/Standard: v2 read/' "$A/Coder/briefing.md"; hook s9 "go on" >/dev/null; out=$(hook s9 "go on")
ok "coder on the current version -> silent about the standard" '[[ "$out" != *"NEW RULE TWO"* ]]'
echo "watchman: $pass pass, $fail fail"; [ $fail = 0 ]
