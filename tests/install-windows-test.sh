#!/usr/bin/env bash
# install.sh on native Windows (Git Bash), imitated on Linux: python3 is the Microsoft Store stub (prints "Python was
# not found", exits 9009), the real Python is `python` (or only `py -3`), and the commands Git for Windows does not
# ship are missing (getent, flock, setsid, crontab, jq, systemctl, sudo, pgrep, ionice, rsync, ...); `ps` refuses -o and
# `ln -s` copies, as MSYS does. MSYSTEM=MINGW64 and an identity cygpath stand in for Git Bash. Every "command not found"
# under bash, anywhere (installer, its checks, hooks), is logged and must not happen. Checks: the installer picks the real Python and puts it
# into the hook commands of settings.json; lib/pyshim/python3 runs it; every hook command runs with nothing in
# hook-errors.log; claim.sh and episodic_append.sh lock without flock; the missing commands are named with the Windows
# way; no working Python at all = a clear stop. And the control: on Linux with python3 nothing of this appears.
# A temp HOME, --no-cron. INSTALL=<path to install.sh> tests another copy. Last line: install-windows-test: N pass, M fail.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
if [[ -z "${INSTALL:-}" ]]; then
  for c in "${CCM_REPO_DIR:-}" "$HERE/.."; do
    [[ -n "$c" && -f "$c/install.sh" && -f "$c/check-install.py" ]] && { INSTALL="$c/install.sh"; break; }
  done
fi
[[ -n "${INSTALL:-}" ]] || { echo "install-windows-test: SKIP (no clone with install.sh: set CCM_REPO_DIR=<clone> - nothing was tested)"; exit 0; }
REAL_PY=$(command -v python3) || { echo "install-windows-test: SKIP (no python3 on this machine)"; exit 0; }
T=$(mktemp -d) || exit 2; [[ -d "$T" ]] || exit 2; trap 'rm -rf "$T"' EXIT
for v in $(compgen -e | grep '^CCM_\|^CLAUDE_METHODOLOGY_\|^PYTHON'); do unset "$v"; done   # a setting from this machine would beat the test's
unset TAVILY_API_KEY EXA_API_KEY CLAUDE_ENV_FILE
export CCM_TEST=1
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "${out:-}" | tail -25 | sed "s/^/   /"; fi; }

fakebin() {  # fakebin <dir> <names to leave out...> - a symlink to every other command on PATH (first one wins, as in PATH)
  local dir="$1" d f n dirs; shift; mkdir -p "$dir"
  local skip=" $* "
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
# Git Bash: what Git for Windows does not ship is absent; python3 = the Store stub (first in PATH, as WindowsApps is);
# python = the real one. ps and ln behave as in MSYS (see below).
ABSENT="getent flock setsid crontab jq systemctl sudo useradd usermod groupadd pgrep pkill ionice timedatectl apt-get rsync logger uuidgen column lsof free ss ip inotifywait notify-send xdg-open"
fakebin "$T/bin" $ABSENT claude python python3 cygpath ps ln
mkdir -p "$T/stub" "$T/win"
printf '#!/bin/sh\nfor a; do case "$a" in -*o*) echo "ps: unknown option -- o" >&2; exit 1;; esac; done\nexec %q "$@"\n' "$(command -v ps)" > "$T/win/ps"
# MSYS without developer mode: ln -s COPIES the target
printf '#!/bin/sh\nsym=0; for a; do case "$a" in -*s*) [ "${a#--}" = "$a" ] && sym=1;; esac; done\nif [ $sym = 1 ]; then set -- $(printf "%%s\\n" "$@" | grep -v "^-"); d=$2; [ -d "$d" ] && d="$d/$(basename "$1")"; rm -rf "$d"; exec cp -r "$1" "$d"; fi\nexec %q "$@"\n' "$(command -v ln)" > "$T/win/ln"
chmod +x "$T/win/ps" "$T/win/ln"
export MISSLOG="$T/missing.log"; : > "$MISSLOG"
command_not_found_handle() { printf '%s\t%s\n' "$1" "$*" >> "$MISSLOG"; echo "bash: $1: command not found" >&2; return 127; }
export -f command_not_found_handle
printf '#!/bin/sh\necho "Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Manage App Execution Aliases." >&2\nexit 9009\n' > "$T/stub/python3"
printf '#!/bin/sh\nshift; printf "%%s\\n" "$1"\n' > "$T/win/cygpath"        # cygpath -m|-u|-w <path> -> <path>
ln -s "$REAL_PY" "$T/win/python"
chmod +x "$T/stub/python3" "$T/win/cygpath"
WINPATH="$T/stub:$T/bin:$T/win"

inst() {  # inst <PATH> <home> [env...] - the install as a person runs it in Git Bash, no questions; VERIFY=1: with the check
  local p="$1" h="$2" v=--no-verify; shift 2; [[ "${VERIFY:-}" == 1 ]] && v=--no-cron
  env "$@" MSYSTEM=MINGW64 HOME="$h" PATH="$p" "$BASH" "$INSTALL" --user --yes --no-cron $v --name tester --workspace "$h/ws" --timezone UTC 2>&1
}
hook_cmds() { "$REAL_PY" -c 'import json,sys
for ev, gs in json.load(open(sys.argv[1])).get("hooks", {}).items():
    for g in gs:
        for h in g.get("hooks", []): print(ev + "\t" + h["command"])' "$1"; }

absent_ok() { local c; for c in $ABSENT; do PATH="$WINPATH" command -v "$c" >/dev/null && return 1; done; return 0; }
ok "0 the fake Git Bash: python3 is the stub (rc 9009), python works, none of the absent commands is there" \
   '! PATH="$WINPATH" python3 -c 1 2>/dev/null && PATH="$WINPATH" python -c 1 && absent_ok && ! PATH="$WINPATH" ps -o pid= -p $$ >/dev/null 2>&1'

H="$T/h1"; mkdir -p "$H"; out=$(VERIFY=1 inst "$WINPATH" "$H"); rc=$?
S="$H/.claude/settings.json"
ok "1 the install with its check goes on with the stub as python3, exit 0, check and supervisor green (rc=$rc)" \
   '[ $rc = 0 ] && [ -f "$S" ] && [ -f "$H/.claude/methodology.conf" ] && grep -q "0 missing or broken" <<<"$out" && grep -q "supervisor: 0 problems, 0 broken" <<<"$out"'
ok "2 it says which Python it took: python" 'grep -q "Python: python (" <<<"$out"'
cmds=$(hook_cmds "$S")
ok "3 every hook command that runs a .py names python before it; none says python3" \
   '[ -n "$cmds" ] && ! grep "\.py\"" <<<"$cmds" | grep -qv "hook-safe.sh\" python \"" && ! grep -q "python3" <<<"$cmds"'
ok "4 settings.json env: PYTHONUTF8=1" '[ "$("$REAL_PY" -c "import json,sys; print(json.load(open(sys.argv[1]))[\"env\"].get(\"PYTHONUTF8\"))" "$S")" = 1 ]'
ok "5 lib/pyshim/python3 runs the real Python, also with the stub first in PATH" \
   '[ "$(PATH="$WINPATH" bash -c ". \"$H/.claude/lib/pyshim/env.sh\"; python3 -c \"print(6*7)\"")" = 42 ] && [ -f "$H/.claude/lib/pyshim/sitecustomize.py" ]'
ok "6 the missing commands: crontab with the Windows way (Task Scheduler); flock, setsid, jq not named" \
   'grep -q "missing: crontab — " <<<"$out" && grep -q "install (Windows, crontab): .*Task Scheduler" <<<"$out" && ! grep -q "missing: flock\|missing: setsid\|missing: jq\|install: apt" <<<"$out"'
ok "7 the stub is not named as missing python3, and no line asks for apt" '! grep -qi "python3 is required\|apt install" <<<"$out"'

# every hook command, as Claude Code runs it through Git Bash (the payloads wintest.sh uses)
n=0; bad=""
while IFS=$'\t' read -r ev cmd; do
  n=$((n+1))
  case $ev in
    PreToolUse|PostToolUse|PostToolUseFailure|PermissionDenied) p='{"session_id":"t","hook_event_name":"'$ev'","tool_name":"Bash","tool_input":{"command":"echo hi"},"tool_response":{"stdout":"hi"},"cwd":"'$T'"}';;
    UserPromptSubmit) p='{"session_id":"t","hook_event_name":"UserPromptSubmit","prompt":"hello","cwd":"'$T'"}';;
    *) p='{"session_id":"t","hook_event_name":"'$ev'","cwd":"'$T'","transcript_path":"'$T'/none.jsonl"}';;
  esac
  printf '%s' "$p" | MSYSTEM=MINGW64 HOME="$H" PATH="$WINPATH" CLAUDE_ENV_FILE="$T/envfile" timeout 60 bash -c "$cmd" >/dev/null 2>&1 \
    || bad="$bad $ev(rc $?)"
done <<<"$cmds"
out=$(cat "$H/.claude/hook-errors.log" 2>/dev/null)
ok "8 all $n hook commands run, exit 0, and hook-errors.log is empty" '[ $n -gt 20 ] && [ -z "$bad" ] && [ -z "$out" ]'
out=$(cat "$T/envfile" 2>/dev/null)
ok "9 a hook hands the shim PATH to the agent's Bash (CLAUDE_ENV_FILE), once" \
   '[ "$(grep -c "lib/pyshim:" <<<"$out")" = 1 ] && [ "$(PATH="$WINPATH" bash -c ". \"$T/envfile\"; python3 -c \"print(1)\"")" = 1 ]'

# the locks without flock: claim.sh and episodic_append.sh from the install, the stub first in PATH
SH="$H/.claude/scripts"; E="$T/ep"
run() { MSYSTEM=MINGW64 HOME="$H" PATH="$H/.claude/lib/pyshim:$WINPATH" "$@" 2>&1; }
out=$(run bash "$SH/claim.sh" acquire k1 --owner a; run bash "$SH/claim.sh" acquire k1 --owner b; echo "rc=$?")
ok "10 claim.sh without flock: the first takes it, the second is refused" 'grep -q "^OK: .k1. for a" <<<"$out" && grep -q "TAKEN" <<<"$out" && grep -q "rc=1" <<<"$out"'
out=$(for i in 1 2 3 4 5 6; do EPISODIC_DIR="$E" run bash "$SH/episodic_append.sh" 2026-11 "entry $i" & done; wait; cat "$E/2026-11.md")
ok "11 episodic_append.sh without flock: 6 writers at once, all 6 entries, no lock folder left" \
   '[ "$(grep -c "^entry [1-6]$" <<<"$out")" = 6 ] && [ -z "$(find "$E" "$H/.claude" -name "*.lock.d")" ]'

# ln -s copies here: ~/.local/bin gets small scripts that run the installed tools; a re-run updates them as its own
out=$(inst "$WINPATH" "$H"); rc=$?
ok "15 re-run: exit 0, ~/.local/bin entries are ours (no 'not ours'), creds and secret-scan run from there (rc=$rc)" \
   '[ $rc = 0 ] && ! grep -q "is not ours" <<<"$out" && grep -q "^# claude-code-methodology: runs" "$H/.local/bin/creds" && echo hi > "$T/clean.txt" && run "$H/.local/bin/secret-scan" "$T/clean.txt" >/dev/null && run "$H/.local/bin/creds" list >/dev/null'

# os.kill(pid, 0) is a liveness probe on Linux and macOS but KILLS the process on Windows (TerminateProcess)
REPO=$(cd "$(dirname "$INSTALL")" && pwd)
out=$(grep -rnE 'os\.kill\([^)]*,\s*0\s*\)' "$REPO"/hooks "$REPO"/scripts "$REPO"/lib "$REPO"/bin "$REPO"/mcp "$REPO"/addons --include='*.py' 2>/dev/null | grep -v '/lib/ccm_proc.py:'; \
      grep -lE '^#!.*python' "$REPO"/bin/* 2>/dev/null | xargs -r grep -nE 'os\.kill\([^)]*,\s*0\s*\)')
ok "16 no os.kill(pid, 0) outside lib/ccm_proc.py (kill0: a probe that does not kill on Windows)" '[ -z "$out" ]'

# only `py -3` (no python, python3 still the stub) -> the launcher with its -3
mkdir -p "$T/py" "$T/win2"; printf '#!/bin/sh\n[ "$1" = -3 ] && shift\nexec %q "$@"\n' "$REAL_PY" > "$T/py/py"; chmod +x "$T/py/py"
ln -s "$T/win/cygpath" "$T/win2/cygpath"; ln -s "$T/win/ps" "$T/win2/ps"; ln -s "$T/win/ln" "$T/win2/ln"
H="$T/h3"; mkdir -p "$H"; out=$(inst "$T/stub:$T/bin:$T/py:$T/win2" "$H"); rc=$?
out2=$(hook_cmds "$H/.claude/settings.json" 2>&1)
ok "12 python absent too: 'py -3' is chosen, in the hook commands and in the shim (rc=$rc)" \
   '[ $rc = 0 ] && grep -q "Python: py -3" <<<"$out" && grep -q "hook-safe.sh\" py -3 \"" <<<"$out2" && [ "$(PATH="$T/stub:$T/bin:$T/py" bash -c ". \"$H/.claude/lib/pyshim/env.sh\"; python3 -c \"print(5)\"")" = 5 ]'

# no working Python at all -> stops, names the stub and how to get Python on Windows
H="$T/h4"; mkdir -p "$H"; out=$(inst "$T/stub:$T/bin:$T/win2" "$H"); rc=$?
ok "13 only the stub: exit non-zero, names the Store stub and winget (rc=$rc)" \
   '[ $rc != 0 ] && grep -q "Microsoft Store stub" <<<"$out" && grep -q "winget install Python" <<<"$out" && [ ! -f "$H/.claude/settings.json" ]'

# control: Linux with a working python3 -> commands as in the template (no interpreter), no pyshim, no PYTHONUTF8
fakebin "$T/lin" claude
H="$T/h5"; mkdir -p "$H"; out=$(HOME="$H" PATH="$T/lin" "$BASH" "$INSTALL" --user --yes --no-cron --no-verify --name tester --workspace "$H/ws" --timezone UTC 2>&1); rc=$?
out2=$(hook_cmds "$H/.claude/settings.json" 2>&1)
ok "14 Linux control: exit 0, hook commands without an interpreter, no lib/pyshim, no PYTHONUTF8 (rc=$rc)" \
   '[ $rc = 0 ] && grep -q "hook-safe.sh\" \"[^\"]*/hooks/[a-z-]*\.py\"" <<<"$out2" && ! grep -q "hook-safe.sh\" python" <<<"$out2" && [ ! -e "$H/.claude/lib/pyshim" ] && ! grep -q PYTHONUTF8 "$H/.claude/settings.json" && ! grep -q "Python: " <<<"$out"'

# (a) a command that is one quoted path ("C:/x/check.sh") came back broken from Python's Windows command line (no space
#     = no outer quotes): on Windows every .sh hook command starts with `bash `, and a bash line from Python travels in
#     the environment (ccm_proc.bash_c), not as an argument
cmds=$(hook_cmds "$T/h1/.claude/settings.json")
ok "18 Windows: every hook command runs its .sh through bash by name (bash \"...sh\")" \
   '[ -n "$cmds" ] && ! cut -f2 <<<"$cmds" | grep -qv "^bash \""'
out=$(cd "$REPO" && "$REAL_PY" - <<'PY' 2>&1
import os, sys
sys.path.insert(0, "lib"); import ccm_proc
real = os.name; ccm_proc.os.name = "nt"
try:
    argv, env = ccm_proc.bash_c('"C:/x/check.sh"')
finally:
    ccm_proc.os.name = real
print("ok" if '"C:/x/check.sh"' not in " ".join(argv) and env.get("CCM_BASH_C") == '"C:/x/check.sh"' else f"bad {argv}")
PY
)
lint=$(grep -nE '\["bash", "-c"|\[bash_exe\(\), "-c"|shell=True' "$REPO"/scripts/supervisor.py "$REPO"/scripts/blockers.py "$REPO"/scripts/presence_check.py 2>/dev/null)
ok "19 bash_c: on Windows the line is in CCM_BASH_C, not in argv; supervisor/blockers/presence use it" '[ "$out" = ok ] && [ -z "$lint" ]'

# (b) autoMemoryDirectory: Windows Python joins C:/x/.claude\memory; a string compare with the shell's path took the
#     default folder for "the person's own" and the setting was never written. Windows path rules (ntpath) here:
out=$(cd "$REPO" && "$REAL_PY" - <<'PY' 2>&1
import ntpath, os, sys
sys.path.insert(0, "lib"); import ccm_conf
os.path = ccm_conf.os.path = ntpath
d, own = ccm_conf.memory_dir_set("C:/Users/x/.claude")
print("ok" if own is False and d.lower().endswith("memory") else f"bad {d!r} own={own}")
PY
)
ok "20 memory folder decided by Python's own path rules: the default C:/x/.claude\\memory is not 'the person's own'" '[ "$out" = ok ]'

# (c) a script run straight from a terminal whose code page cannot print "→" (cp1251), without PYTHONUTF8
cp() { env -u PYTHONUTF8 PYTHONIOENCODING=cp1251 MSYSTEM=MINGW64 HOME="$T/h1" PATH="$WINPATH" "$@" 2>&1; }
out=$(cp python "$REPO/check-install.py" --user; echo "rc=$?")
ok "21 check-install.py --user with a cp1251 console: no UnicodeEncodeError, exit 0, the arrows printed" \
   '! grep -q UnicodeEncodeError <<<"$out" && grep -q "rc=0" <<<"$out" && grep -q "→" <<<"$out"'
out=$(for f in lib/deps_check.py scripts/quota_status.py scripts/verify_prompt.py scripts/watchman_alive_check.py; do cp python "$REPO/$f" --help; done; echo x | cp python "$REPO/bin/secret-scan")
ok "22 other scripts people run by hand: no UnicodeEncodeError with a cp1251 console" '! grep -q UnicodeEncodeError <<<"$out"'

out=$(cut -f2 "$MISSLOG" | sort | uniq -c)
ok "17 no command was missing anywhere above (installer, its check, every hook, the scripts): bash logged no 'command not found'" '[ ! -s "$MISSLOG" ]'

echo "install-windows-test: $pass pass, $fail fail"; [ $fail = 0 ]
