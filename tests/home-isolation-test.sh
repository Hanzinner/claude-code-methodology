#!/usr/bin/env bash
# No test writes into the person's home - imitated as on Windows. Python on Windows takes "~" from USERPROFILE and
# ignores HOME, while every test isolates itself with HOME=<temp dir>: on a real machine the tests' Python wrote into
# the person's real ~/.claude (two test reminders stayed). Here USERPROFILE points at a trap folder (the "real home"),
# and a sitecustomize makes this Linux Python resolve "~" the Windows way (USERPROFILE, else HOMEDRIVE+HOMEPATH; HOME
# ignored). The repo's lib/pyshim/sitecustomize.py runs after it, as it does on Windows (env.sh puts it on PYTHONPATH).
# Every other test of the repo runs like that; after each one the trap must be empty - the culprits are named.
# Their own pass/fail is not judged here (each has its own run). ONLY=<test file names> runs just those.
# CCM_REPO_DIR=<clone> tests another copy. Last line: home-isolation: N pass, M fail.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$HERE/..
[[ -n "${CCM_REPO_DIR:-}" ]] && REPO=$CCM_REPO_DIR
. "$REPO/lib/ccm_compat.sh"
[[ -f "$REPO/lib/ccm_conf.py" ]] || { echo "home-isolation: SKIP (no lib/ccm_conf.py in $REPO - nothing was tested)"; exit 0; }
T=$(mktemp -d) || exit 2; [[ -d "$T" ]] || exit 2; trap 'rm -rf "${T:?}"' EXIT
TRAP="$T/real-home"; mkdir -p "$TRAP" "$T/sim"
cat > "$T/sim/sitecustomize.py" <<'PY'
# Windows home rules for this Linux Python (home-isolation-test): "~" = USERPROFILE, else HOMEDRIVE+HOMEPATH.
import os, posixpath, sys
def _win_home():
    return os.environ.get("USERPROFILE") or (os.environ.get("HOMEDRIVE", "") + os.environ.get("HOMEPATH", "")) or None
_real = posixpath.expanduser
def expanduser(path):
    p = os.fspath(path)
    t, sl = ("~", "/") if isinstance(p, str) else (b"~", b"/")
    h = _win_home()
    if h is None or not (p == t or p.startswith(t + sl)):
        return _real(p) if p.startswith(t) and h is not None else p   # "~user" - not used by the repo
    return (h if isinstance(p, str) else os.fsencode(h)) + p[1:]
posixpath.expanduser = os.path.expanduser = expanduser
# then the repo's own sitecustomize, as on Windows
_pyshim = os.environ.get("HOME_ISO_PYSHIM")
if _pyshim and os.path.isfile(os.path.join(_pyshim, "sitecustomize.py")):
    with open(os.path.join(_pyshim, "sitecustomize.py"), encoding="utf-8") as _f:
        exec(compile(_f.read(), os.path.join(_pyshim, "sitecustomize.py"), "exec"), {"__name__": "sitecustomize_repo"})
PY
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; [[ -n "${3:-}" ]] && echo "$3" | sed 's/^/   /'; fi; }

# On a real Windows (Git Bash) Python already resolves "~" this way: no imitation, only the trap and the runs below.
WIN=0; case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) WIN=1 ;; esac; [[ -n "${MSYSTEM:-}" ]] && WIN=1
[[ $WIN = 1 ]] && { : > "$T/sim/sitecustomize.py"; TRAP=$(cygpath -m "$TRAP" 2>/dev/null || echo "$TRAP"); }
# the imitation itself: "~" follows USERPROFILE and not HOME; without the repo's rule a test's HOME is ignored
nrm() { local p; p=$(cygpath -m "$1" 2>/dev/null || printf '%s' "$1"); p=${p//\\//}; printf '%s\n' "${p%/}"; }   # one path form (Windows)
sim() { env HOME="$1" USERPROFILE="$TRAP" PYTHONPATH="$T/sim" HOME_ISO_PYSHIM="${2:-}" python3 -c 'import os; print(os.path.expanduser("~/.claude"))'; }
[[ $WIN = 1 ]] && echo "SKIP on Windows: 0 (the imitation of Windows home rules - here they are real)" || \
ok "0 the imitation: HOME is ignored, \"~\" = USERPROFILE (as Windows Python does)" '[ "$(sim "$T/h0")" = "$TRAP/.claude" ]'
ok "0b with the repo's sitecustomize: \"~\" follows HOME (one home for bash and Python)" '[ "$(nrm "$(sim "$T/h0" "$REPO/lib/pyshim")")" = "$(nrm "$T/h0/.claude")" ]'
out=$(env HOME="$T/h0" USERPROFILE="$TRAP" PYTHONPATH="$T/sim" python3 -c "import sys; sys.path.insert(0, sys.argv[1]); import ccm_conf; print(ccm_conf.HOME)" "$REPO/lib")   # a path as an argument: Git Bash converts it for Windows Python, not inside -c
ok "0c lib/ccm_conf.py alone (no sitecustomize): its HOME follows HOME too" '[ "$(nrm "$out")" = "$(nrm "$T/h0")" ]' "$out"

# Each test gets its own trap folder, so they run 4 at a time (the whole suite one by one is ~8 min) and a leak still
# names its test.
one() {   # one <test file>
  local t=$1 b=${1##*/} r
  case $b in *.py) r=(python3 "$t") ;; *) r=(bash "$t") ;; esac
  mkdir -p "$TRAP/$b"
  # ccm_timeout (lib/ccm_compat.sh): a stock macOS has no `timeout` - with it the nested run was "command not found"
  # and the test passed without running anything; a shell function can't follow env, so env goes after it
  ( cd "$T" && ccm_timeout 600 env USERPROFILE="$TRAP/$b" PYTHONPATH="$T/sim${PYTHONPATH:+:$PYTHONPATH}" \
      HOME_ISO_PYSHIM="$REPO/lib/pyshim" CCM_REPO_DIR="$REPO" CCM_TEST=1 "${r[@]}" >/dev/null 2>&1 )
}
n=0
for t in "$REPO"/tests/*-test.sh "$REPO"/tests/*-test.py; do
  b=${t##*/}
  case $b in home-isolation-test.sh) continue ;; esac
  [[ -n "${ONLY:-}" && " $ONLY " != *" $b "* ]] && continue
  n=$((n+1)); one "$t" &
  while (( $(jobs -rp | wc -l) >= 4 )); do wait -n 2>/dev/null || wait; done
done
wait
leaks=$(cd "$TRAP" && for d in *; do [[ -d "$d" ]] || continue; got=$(cd "$d" && find . -mindepth 1 | head -5 | tr '\n' ' '); [[ -n "$got" ]] && echo "$d: $got"; done)
ok "1 after each of $n tests the trap (the person's home as Windows Python sees it) is empty" '[ -z "$leaks" ] && [ $n -gt 0 ]' "$leaks"
echo "home-isolation: $pass pass, $fail fail"; [ $fail = 0 ]
