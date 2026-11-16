#!/usr/bin/env bash
# sandbox_guard_lint.py: a temp dir from mktemp -d must be checked before use. A test with a trimmed PATH (no mktemp) once
# left T="" and, run as root, wrote "$T/bin/rsync" = /bin/rsync over the system binary; set -u does not catch an empty value.
# 1) synthetic cases: unchecked -> red; || exit / || <function> / -d "$T" / set -e -> quiet; local under set -e, || true -> red.
# 2) this repo: no unchecked mktemp -d in any bash file - a new one turns this test red. LINT=<path> tests another copy.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
LINT=${LINT:-$REPO/scripts/sandbox_guard_lint.py}
T=$(mktemp -d) || exit 2; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1 :: ${3:-}"; fi; }
case_() { printf '%s\n' "$2" > "$T/$1.sh"; python3 "$LINT" "$T/$1.sh" >/dev/null; echo $?; }

ok "1 T=\$(mktemp -d) unchecked -> red" '[[ $(case_ a "T=\$(mktemp -d); echo x > \"\$T/f\"") == 1 ]]'
ok "2 || exit 2 -> quiet" '[[ $(case_ b "T=\$(mktemp -d) || exit 2; trap x EXIT") == 0 ]]'
ok "3 && [[ -d \"\$T\" ]] on the same line -> quiet" '[[ $(case_ c "T=\$(mktemp -d) && [[ -d \"\$T\" && \"\$T\" != / ]] || exit 2") == 0 ]]'
ok "4 a -n \"\$W\" test on the next line -> quiet" '[[ $(case_ d "W=\$(mktemp -d -p /var/tmp)
[ -n \"\$W\" ] || exit 2") == 0 ]]'
ok "5 set -euo pipefail above -> quiet" '[[ $(case_ e "set -euo pipefail
T=\$(mktemp -d)") == 0 ]]'
ok "6 local under set -e (local hides the exit code) -> red" '[[ $(case_ f "set -e
f() { local d=\$(mktemp -d); cp x \"\$d\"; }") == 1 ]]'
ok "7 in the middle of a line (A=1; W=\$(mktemp -d); ...) -> red" '[[ $(case_ g "SRC=x; W=\$(mktemp -d); pass=0") == 1 ]]'
ok "8 a commented-out line -> quiet" '[[ $(case_ h "# T=\$(mktemp -d)") == 0 ]]'
ok "9 || finish (a function that exits) -> quiet; || true -> red" '[[ $(case_ i "tmp=\$(mktemp -d) || finish") == 0 && $(case_ j "tmp=\$(mktemp -d) || true") == 1 ]]'
ok "10 export HOME=\$(mktemp -d) unchecked -> red" '[[ $(case_ k "export HOME=\$(mktemp -d) X=1") == 1 ]]'
o=$(python3 "$LINT" "$T/g.sh"); ok "11 output: file:line: text" '[[ "$o" == "$T/g.sh:1: SRC=x; W="* ]]' "$o"
files=()
while IFS= read -r -d '' f; do head -c 64 "$f" 2>/dev/null | grep -q '^#!.*bash' && files+=("$f"); done \
  < <(find "$REPO" -path "$REPO/.git" -prune -o -type f \( -name '*.sh' -o -perm -u+x \) -print0)
o=$(python3 "$LINT" "${files[@]}"); rc=$?
ok "12 every bash file of this repo (${#files[@]}) checks its mktemp -d" '[[ $rc == 0 && ${#files[@]} -gt 50 ]]' "$o"
echo "sandbox-guard-lint: $pass pass, $fail fail"; (( fail == 0 ))
