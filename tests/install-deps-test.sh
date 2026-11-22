#!/usr/bin/env bash
# install.sh and check-install.py on a machine without flock, timeout, setsid and crontab: the install goes on (exit 0)
# and names each missing command that stops something (timeout, crontab) with what stops and how to install it; flock
# and setsid have fallbacks (a mkdir lock, a reader started without setsid), so they are not named. A fake bin dir links every
# command on PATH except those (and claude: nothing outside the sandbox is asked). A temp HOME, --no-cron.
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

fakebin "$T/bin" flock timeout setsid crontab claude
ok "0 the fake PATH lacks flock/timeout/setsid/crontab, has python3" \
   '[ ! -e "$T/bin/flock" ] && [ ! -e "$T/bin/timeout" ] && [ ! -e "$T/bin/setsid" ] && [ ! -e "$T/bin/crontab" ] && [ -x "$T/bin/python3" ]'

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

echo "install-deps-test: $pass pass, $fail fail"; [ $fail = 0 ]
