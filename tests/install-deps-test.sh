#!/usr/bin/env bash
# install.sh and check-install.py on a machine without flock, timeout, setsid and crontab: the install goes on (exit 0)
# and names each missing command that stops something (timeout, crontab) with what stops and how to install it; flock
# and setsid have fallbacks (a mkdir lock, a reader started without setsid), so they are not named; timeout has one too
# (gtimeout, perl: lib/ccm_compat.sh), so it is named only when perl is missing as well. A fake bin dir links every
# command on PATH except those (and claude: nothing outside the sandbox is asked). A temp HOME, --no-cron.
# bash: lib/deps_check.py with stand-in bashes (CCM_BASH_PROBE = the bashes hooks may run under, CCM_BASH_CANDIDATES =
# where a newer one may be; a stand-in is a 2-line sh script that prints a version): 3.x and no newer -> "missing: bash
# 4+"; 3.x and a newer one -> no line, --hook-bash names it and install.sh starts every hook command through it.
# INSTALL=<path to install.sh> tests another copy (its folder must be a whole clone). Last line: install-deps-test: N pass, M fail.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
if [[ -z "${INSTALL:-}" ]]; then
  for c in "${CCM_REPO_DIR:-}" "$HERE/.."; do
    [[ -n "$c" && -f "$c/install.sh" && -f "$c/check-install.py" ]] && { INSTALL="$c/install.sh"; break; }
  done
fi
[[ -n "${INSTALL:-}" ]] || { echo "install-deps-test: SKIP (no clone with install.sh: set CCM_REPO_DIR=<clone> - nothing was tested)"; exit 0; }
REPO=$(cd "$(dirname "$INSTALL")" && pwd)
T=$(mktemp -d) || exit 2; [[ -d "$T" ]] || exit 2; trap 'rm -rf "$T"' EXIT
for v in $(compgen -e | grep '^CCM_\|^CLAUDE_METHODOLOGY_'); do unset "$v"; done   # a setting from this machine would beat the test's
unset TAVILY_API_KEY EXA_API_KEY
export CCM_TEST=1
# stand-in bashes; the cases 0-10 run with a 4+ one, so the bash check stays out of their way on any machine (a Mac
# whose /bin/bash is 3.2 included)
mkdir -p "$T/fb"
printf '#!/bin/sh\necho 3\n' > "$T/fb/bash3"; printf '#!/bin/sh\necho 5\n' > "$T/fb/bash5"; chmod +x "$T/fb/bash3" "$T/fb/bash5"
export CCM_BASH_PROBE="$T/fb/bash5"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | tail -25 | sed "s/^/   /"; fi; }

fakebin() {  # fakebin <dir> <names to leave out...> - a symlink to every other command on PATH (first one wins, as in PATH)
  local dir="$1" d f n dirs; shift; mkdir -p "$dir"
  local skip=" $* "                                  # before IFS changes: "$*" joins with the first char of IFS
  IFS=: read -ra dirs <<<"$PATH"
  for d in "${dirs[@]}"; do
    [[ -d "$d" ]] || continue
    for f in "$d"/*; do
      n=${f##*/}
      [[ -f "$f" && -x "$f" && ! -e "$dir/$n" ]] || continue
      case "$skip" in *" $n "*) continue ;; esac
      ln -s "$f" "$dir/$n"
    done
  done
}
inst() {  # inst <bin dir> <home> - the install as a person runs it, no questions
  HOME="$2" PATH="$1" "$BASH" "$INSTALL" --user --yes --no-cron --no-verify --name tester --workspace "$2/ws" --timezone UTC 2>&1
}

fakebin "$T/bin" flock timeout gtimeout perl setsid crontab claude
ok "0 the fake PATH lacks flock/timeout/gtimeout/perl/setsid/crontab, has python3" \
   '[ ! -e "$T/bin/flock" ] && [ ! -e "$T/bin/timeout" ] && [ ! -e "$T/bin/perl" ] && [ ! -e "$T/bin/setsid" ] && [ ! -e "$T/bin/crontab" ] && [ -x "$T/bin/python3" ]'

mkdir -p "$T/h1"; out=$(inst "$T/bin" "$T/h1"); rc=$?
ok "1 no flock/timeout/setsid/crontab -> the install goes on, exit 0 (rc=$rc)" '[ $rc = 0 ] && [ -f "$T/h1/.claude/settings.json" ] && [ -f "$T/h1/.claude/hooks/hook-safe.sh" ]'
ok "2 a 'missing:' line for timeout and crontab; none for flock, setsid (they have fallbacks)" \
   'grep -q "^ *missing: timeout — " <<<"$out" && grep -q "^ *missing: crontab — " <<<"$out" && ! grep -q "missing: flock\|missing: setsid" <<<"$out"'
ok "3 each line names what stops: timeout -> hook-safe.sh, crontab -> the scheduled jobs" \
   'grep "missing: timeout" <<<"$out" | grep -q "hook-safe.sh" && grep "missing: crontab" <<<"$out" | grep -q "scheduled job"'
ok "4 commands that are there are not listed (python3)" '! grep -q "missing: python3" <<<"$out"'
ok "5 ONE install line, with the packages for apt and brew" \
   '[ "$(grep -c "^ *install: apt install" <<<"$out")" = 1 ] && grep "install: apt install" <<<"$out" | grep -q "coreutils" && grep "install: apt install" <<<"$out" | grep -q "cron" && grep "install: apt install" <<<"$out" | grep -q "brew install .*coreutils"'
ok "6 the block comes at the start, before anything is installed" \
   '[ "$(grep -n "missing: timeout" <<<"$out" | head -1 | cut -d: -f1)" -lt "$(grep -n "Installing to:" <<<"$out" | head -1 | cut -d: -f1)" ]'
ok "7 the end repeats which commands are missing (the top has scrolled away)" 'grep -q "Missing system commands: timeout crontab" <<<"$out"'

out=$(HOME="$T/h1" PATH="$T/bin" python3 "$REPO/check-install.py" --user 2>&1)
ok "8 check-install.py prints the same block" \
   'grep -q "^System commands missing" <<<"$out" && grep -q "^ *missing: timeout — .*hook-safe.sh" <<<"$out" && grep -q "^ *missing: crontab — " <<<"$out" && grep -q "^ *install: apt install" <<<"$out"'

# control: everything there (except claude) -> not a word about missing commands
fakebin "$T/bin2" claude
mkdir -p "$T/h2"; out=$(inst "$T/bin2" "$T/h2"); rc=$?
ok "9 all commands there -> exit 0 and no 'missing:' (rc=$rc)" '[ $rc = 0 ] && ! grep -q "missing:\|Missing system commands" <<<"$out"'
out=$(HOME="$T/h2" PATH="$T/bin2" python3 "$REPO/check-install.py" --user 2>&1)
ok "10 check-install.py with all commands there -> no block" '! grep -q "System commands missing\|missing: " <<<"$out"'

# timeout: perl is its fallback (lib/ccm_compat.sh), so no timeout + perl there -> not named
fakebin "$T/bin3" timeout gtimeout claude
if [ -e "$T/bin3/perl" ]; then
  out=$(PATH="$T/bin3" python3 "$REPO/lib/deps_check.py" 2>&1)
  ok "11 no timeout, perl there -> no 'missing: timeout' (perl's alarm is the fallback)" '! grep -q "missing: timeout" <<<"$out"'
else echo "install-deps-test: no perl on this machine - case 11 skipped"; fi

# bash older than 4 (a stock macOS) - lib/deps_check.py with stand-in bashes
DC="$REPO/lib/deps_check.py"
out=$(CCM_BASH_PROBE="$T/fb/bash3" CCM_BASH_CANDIDATES="" python3 "$DC" 2>&1)
ok "12 hooks' bash is 3.x and no newer one -> 'missing: bash 4+' naming it, what stops, brew install bash coreutils" \
   'grep -q "^missing: bash 4+ — .*bash3 is 3.x" <<<"$out" && grep "missing: bash 4+" <<<"$out" | grep -q "hook-safe.sh" && grep "^install:" <<<"$out" | grep -q "brew install.* bash" && grep "^install:" <<<"$out" | grep -q "coreutils"'
out=$(CCM_BASH_PROBE="$T/fb/bash3" CCM_BASH_CANDIDATES="" python3 "$DC" --hook-bash 2>&1)
ok "13 ... and --hook-bash prints nothing (no bash to name)" '[ -z "$out" ]'
out=$(CCM_BASH_PROBE="$T/fb/bash3" CCM_BASH_CANDIDATES="$T/fb/bash3:$T/fb/bash5" python3 "$DC" 2>&1)
ok "14 3.x, but a newer bash exists -> no 'missing: bash' line" '! grep -q "missing: bash" <<<"$out"'
out=$(CCM_BASH_PROBE="$T/fb/bash3" CCM_BASH_CANDIDATES="$T/fb/bash3:$T/fb/bash5" python3 "$DC" --hook-bash 2>&1)
ok "15 ... and --hook-bash names the newer one by its full path" '[ "$out" = "$T/fb/bash5" ]'
out=$(CCM_BASH_PROBE="$T/fb/bash5" CCM_BASH_CANDIDATES="$T/fb/bash5" python3 "$DC" --hook-bash 2>&1)
ok "16 hooks' bash is already 4+ (Linux) -> --hook-bash prints nothing: the hook commands stay as they are" '[ -z "$out" ]'

# the install itself: hook commands start through the newer bash, by its full path
mkdir -p "$T/h3"
out=$(export CCM_BASH_PROBE="$T/fb/bash3" CCM_BASH_CANDIDATES="$T/fb/bash5"; inst "$T/bin2" "$T/h3"); rc=$?
# python3 -c, not a here-document inside $(...): this test runs on a Mac too, and bash 3.2 parses those badly
bad=$(python3 -c 'import json, sys
s = json.load(open(sys.argv[1])); want = chr(34) + sys.argv[2] + chr(34) + " "
cmds = [h["command"] for gs in s["hooks"].values() for g in gs for h in g.get("hooks", [])]
print("\n".join(c for c in cmds if not c.startswith(want)) if cmds else "no hook commands")' "$T/h3/.claude/settings.json" "$T/fb/bash5" 2>&1)
ok "17 install with bash 3.x + a newer bash: exit 0, every hook command starts with that bash (rc=$rc)" \
   '[ $rc = 0 ] && [ -z "$bad" ] && grep -q "hooks and scheduled .sh jobs will run under $T/fb/bash5" <<<"$out"'
out=$(python3 -c 'import json,sys; s=json.load(open(sys.argv[1])); print("\n".join(h["command"] for gs in s["hooks"].values() for g in gs for h in g.get("hooks", [])))' "$T/h2/.claude/settings.json" 2>&1)
ok "18 control (bash 4+): hook commands start with the hook path, no bash in front" '[ -n "$out" ] && ! grep -qE "bash5|bash3" <<<"$out" && ! grep -qv "^\"" <<<"$out"'

echo "install-deps-test: $pass pass, $fail fail"; [ $fail = 0 ]
