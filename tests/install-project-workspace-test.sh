#!/usr/bin/env bash
# install.sh --project <dir>: the workspace (AGENTS.md, MISTAKES.md, LIBRARY.md, Agents/, the shared documents) goes to
# ~/claude-workspace/<dir's name>, outside the person's repo, so their git status shows only .claude/; the project's
# settings.json lists it in permissions.additionalDirectories; the end of the run names it; check-install.py passes;
# a second project with the same folder name gets its own workspace; --workspace <dir> puts it in the repo as before.
# A temp HOME, --no-cron, claude left off PATH (nothing outside the sandbox is asked).
# INSTALL=<path to install.sh> tests another copy (its folder must be a whole clone). Last line: install-project-workspace-test: N pass, M fail.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
if [[ -z "${INSTALL:-}" ]]; then
  for c in "${CCM_REPO_DIR:-}" "$HERE/.."; do
    [[ -n "$c" && -f "$c/install.sh" && -f "$c/check-install.py" ]] && { INSTALL="$c/install.sh"; break; }
  done
fi
[[ -n "${INSTALL:-}" ]] || { echo "install-project-workspace-test: SKIP (no clone with install.sh: set CCM_REPO_DIR=<clone> - nothing was tested)"; exit 0; }
REPO=$(cd "$(dirname "$INSTALL")" && pwd)
T=$(mktemp -d) || exit 2; [[ -d "$T" && "$T" != / ]] || exit 2; trap 'rm -rf "$T"' EXIT
for v in $(compgen -e | grep -e '^CCM_' -e '^CLAUDE_METHODOLOGY_'); do unset "$v"; done   # a setting from this machine would beat the test's
unset TAVILY_API_KEY EXA_API_KEY
export CCM_TEST=1
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | tail -8 | sed "s/^/   /"; fi; }

B="$T/bin"; mkdir -p "$B"
IFS=: read -ra dirs <<<"$PATH"
for d in "${dirs[@]}"; do   # every command on PATH except claude (first one wins, as in PATH)
  [[ -d "$d" ]] || continue
  for f in "$d"/*; do n=${f##*/}; [[ -f "$f" && -x "$f" && ! -e "$B/$n" && "$n" != claude ]] && ln -s "$f" "$B/$n"; done
done
H="$T/home"; mkdir -p "$H"
inst() { HOME="$H" PATH="$B" "$BASH" "$INSTALL" --yes --no-cron --no-verify --name tester --timezone UTC "$@" 2>&1; }
extra() { python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1])).get("permissions", {}).get("additionalDirectories", [])))' "$1/.claude/settings.json" 2>/dev/null; }
SWARM="AGENTS.md MISTAKES.md LIBRARY.md Agents"
has_all() { local n; for n in $SWARM; do [ -e "$1/$n" ] || return 1; done; }    # has_all <dir>
has_none() { local n; for n in $SWARM; do [ ! -e "$1/$n" ] || return 1; done; }  # has_none <dir>

P="$T/code/proj"; mkdir -p "$P"; git -C "$P" init -q
out=$(inst --project "$P"); rc=$?
W="$H/claude-workspace/proj"
ok "1 --project -> exit 0 (rc=$rc)" '[ $rc = 0 ] && [ -f "$P/.claude/settings.json" ]'
ok "2 nothing of the workspace in the project's root" 'has_none "$P"'
st=$(git -C "$P" status --porcelain --untracked-files=normal)
ok "3 the project's git status shows only .claude/" '[ "$st" = "?? .claude/" ]'
ok "4 the workspace files are in ~/claude-workspace/proj" 'has_all "$W"'
ok "5 methodology.conf names that workspace" 'grep -q "^CCM_WORKSPACE=.*$W" "$P/.claude/methodology.conf"'
ok "6 the end of the run names the workspace" 'grep -q "Workspace (agent folders, mistakes journal, shared documents): $W" <<<"$out"'
ok "7 settings.json: the workspace in permissions.additionalDirectories" '[ "$(extra "$P")" = "$W" ]'
out=$(HOME="$H" PATH="$B" python3 "$REPO/check-install.py" --project "$P" 2>&1); rc=$?
ok "8 check-install.py --project passes (rc=$rc)" '[ $rc = 0 ] && grep -q " 0 missing or broken" <<<"$out"'

out=$(inst --project "$P"); rc=$?
ok "9 a re-run keeps the workspace and lists it once (rc=$rc)" '[ $rc = 0 ] && [ "$(extra "$P")" = "$W" ] && [ ! -e "$H/claude-workspace/proj-"* ]'

P2="$T/other/proj"; mkdir -p "$P2"
out=$(inst --project "$P2"); rc=$?
W2=$(sed -n 's/^CCM_WORKSPACE=//p' "$P2/.claude/methodology.conf" | tr -d "'\"")
ok "10 a second project with the same folder name -> its own workspace (rc=$rc, $W2)" \
   '[ $rc = 0 ] && [[ "$W2" == "$H/claude-workspace/proj-"???????? ]] && [ -e "$W2/MISTAKES.md" ] && [ "$(cat "$W/.ccm-project")" = "$P" ]'

P3="$T/code/inrepo"; mkdir -p "$P3"
out=$(inst --project "$P3" --workspace "$P3"); rc=$?
ok "11 --workspace <the project dir> -> the files in the project, as before (rc=$rc)" \
   '[ $rc = 0 ] && has_all "$P3" && [ ! -e "$H/claude-workspace/inrepo" ]'
ok "12 ... no additionalDirectories then, and the end says it is inside the project" \
   '[ -z "$(extra "$P3")" ] && grep -q "inside your project" <<<"$out"'
out=$(HOME="$H" PATH="$B" python3 "$REPO/check-install.py" --project "$P3" 2>&1); rc=$?
ok "13 check-install.py passes for it too (rc=$rc)" '[ $rc = 0 ]'

out=$(inst --user --workspace "$H/ws"); rc=$?
ok "14 --user is unchanged: the workspace where --workspace says, no additionalDirectories (rc=$rc)" \
   '[ $rc = 0 ] && [ -e "$H/ws/MISTAKES.md" ] && ! grep -q additionalDirectories "$H/.claude/settings.json"'

echo "install-project-workspace-test: $pass pass, $fail fail"; [ $fail = 0 ]
