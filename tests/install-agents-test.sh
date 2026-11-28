#!/usr/bin/env bash
# install.sh and agents/: every agents/*.md of the repo lands in <target>/agents/; your own agent files there are left
# as they are; a repo agent you changed is backed up under .methodology-installed/backups/<time>/agents/ (never inside
# agents/: Claude Code would load the copy as a second agent) and replaced; --dry-run changes nothing.
# A temp HOME, --no-cron, claude left off PATH. INSTALL=<path to install.sh> tests another copy (its folder must be a
# whole clone). Last line: install-agents-test: N pass, M fail.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
if [[ -z "${INSTALL:-}" ]]; then
  for c in "${CCM_REPO_DIR:-}" "$HERE/.."; do
    [[ -n "$c" && -f "$c/install.sh" && -d "$c/agents" ]] && { INSTALL="$c/install.sh"; break; }
  done
fi
[[ -n "${INSTALL:-}" ]] || { echo "install-agents-test: SKIP (no clone with install.sh and agents/: set CCM_REPO_DIR=<clone> - nothing was tested)"; exit 0; }
REPO=$(cd "$(dirname "$INSTALL")" && pwd)
T=$(mktemp -d) || exit 2; [[ -d "$T" && "$T" != / ]] || exit 2; trap 'rm -rf "$T"' EXIT
for v in $(compgen -e | grep -e '^CCM_' -e '^CLAUDE_METHODOLOGY_'); do unset "$v"; done   # a setting from this machine would beat the test's
unset TAVILY_API_KEY EXA_API_KEY
export CCM_TEST=1 CCM_WORKSPACE="$T/ws"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | tail -8 | sed "s/^/   /"; fi; }

B="$T/bin"; mkdir -p "$B"
IFS=: read -ra dirs <<<"$PATH"
for d in "${dirs[@]}"; do   # every command on PATH except claude (first one wins, as in PATH)
  [[ -d "$d" ]] || continue
  for f in "$d"/*; do n=${f##*/}; [[ -f "$f" && -x "$f" && ! -e "$B/$n" && "$n" != claude ]] && ln -s "$f" "$B/$n"; done
done
H="$T/home"; mkdir -p "$H" "$T/ws"
inst() { HOME="$H" PATH="$B" "$BASH" "$INSTALL" --user --yes --no-cron --no-verify --name tester --timezone UTC "$@" 2>&1; }
A="$H/.claude/agents"
same_all() { local f; for f in "$REPO"/agents/*.md; do cmp -s "$f" "$A/${f##*/}" || return 1; done; }

out=$(inst); rc=$?
ok "1 install -> exit 0 (rc=$rc)" '[ $rc = 0 ]'
ok "2 every agents/*.md of the repo is installed, byte for byte" 'ls "$REPO"/agents/*.md >/dev/null 2>&1 && same_all'

R1=$(ls "$REPO"/agents/*.md | head -1); N1=${R1##*/}
echo "my own reviewer tweak" >> "$A/$N1"
printf -- '---\nname: mine\ndescription: my own agent\n---\nmine\n' > "$A/mine.md"
cp -p "$A/mine.md" "$T/mine.orig"
out=$(inst --dry-run); rc=$?
ok "3 --dry-run -> exit 0, prints the backup and the copy, changes nothing (rc=$rc)" \
   '[ $rc = 0 ] && grep -q "DRY:.*agents/$N1" <<<"$out" && grep -q "my own reviewer tweak" "$A/$N1"'

out=$(inst); rc=$?
bk=$(ls -d "$H"/.claude/.methodology-installed/backups/*/agents 2>/dev/null | head -1)
ok "4 a changed repo agent is backed up outside agents/ (rc=$rc)" '[ -n "$bk" ] && grep -q "my own reviewer tweak" "$bk/$N1"'
ok "5 ... and replaced with the repo version" 'cmp -s "$R1" "$A/$N1"'
ok "6 the installer says it backed it up" 'grep -q "backed up your changed agents/$N1" <<<"$out"'
ok "7 your own agent file is untouched" 'cmp -s "$T/mine.orig" "$A/mine.md"'
extra=$(ls "$A" | grep -v -x -e mine.md $(for f in "$REPO"/agents/*.md; do printf -- '-e %s ' "${f##*/}"; done))
ok "8 no backup or other copy left inside agents/" '[ -z "$extra" ]'

nb=$(ls -d "$H"/.claude/.methodology-installed/backups/*/agents 2>/dev/null | wc -l)
out=$(inst); rc=$?
nb2=$(ls -d "$H"/.claude/.methodology-installed/backups/*/agents 2>/dev/null | wc -l)
ok "9 an unchanged agent is not backed up again (rc=$rc, $nb -> $nb2)" '[ $rc = 0 ] && [ "$nb" = "$nb2" ]'

echo "install-agents-test: $pass pass, $fail fail"
[ $fail = 0 ]
