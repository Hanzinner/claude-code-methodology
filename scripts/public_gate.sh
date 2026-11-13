#!/usr/bin/env bash
# public_gate.sh <snapshot-dir> | --selftest - the gate BEFORE a public push of a repo snapshot.
# Guards: what must not leave the machine: (1) Cyrillic anywhere in tracked files (CCM_PUBLIC_GATE_CYRILLIC=1, default on),
# (2) people/project names from CCM_PUBLIC_GATE_NAMES (regex alternation, e.g. "Alice|Bob|Acme"; empty = check skipped),
# (3) the HISTORY, not just the current tree: everything that is pushed goes out with the whole history,
# (4) internal swarm files that do not belong outside (CCM_PUBLIC_GATE_INTERNAL, default
#     "AGENT-NOTES|TODO\.md|inbox|briefing|MISTAKES|\.agent-lock"), (5) secrets (key formats).
# BLOCKING: the price of a mistake is irreversible - what is published cannot be recalled.
# Exit: 0 clean, push allowed | 1 found, push forbidden | 2 usage.
# False-green guard: a check with nothing to check always passes, so seeing fewer than 5 tracked files = a BROKEN gate.
# Self-check: before every real run the gate runs its own --selftest matrix; a broken gate refuses to work
# (a gate that cannot fail is worse than none). Every matrix case differs by ONE feature and checks WHICH check fired.
# The locale is part of the tool, not of the environment: without UTF-8 `grep -P '\p{L}'` goes bytewise, and a cron run
# under an empty environment failed the whole matrix.
# Test: tests/public-gate-test.sh. Nightly self-test: public_gate_selftest.sh.
set -uo pipefail
export LC_ALL=C.UTF-8 LANG=C.UTF-8
HERE=$(dirname "$(readlink -f "$0")")
eval "$(python3 "$HERE/../lib/ccm_conf.py" --shell)"
CYR=${CCM_PUBLIC_GATE_CYRILLIC:-1}
NAMES=${CCM_PUBLIC_GATE_NAMES:-}
INTERNAL=${CCM_PUBLIC_GATE_INTERNAL:-'AGENT-NOTES|TODO\.md|inbox|briefing|MISTAKES|\.agent-lock'}
# git through a wrapper: the repo may belong to another user, and without this git silently refuses and returns NOTHING -
# and "nothing" counts as "clean" (this is how an earlier gate lied "green" on its first run)
git() { command git -c safe.directory='*' "$@"; }

if [ "${1:-}" != "--selftest" ] && [ -z "${GATE_SELFCHECK_DONE:-}" ]; then
    if ! GATE_SELFCHECK_DONE=1 "$0" --selftest >/dev/null 2>&1; then
        echo "GATE BROKEN: its own self-test matrix fails - do not use it."
        echo "     Diagnosis: $0 --selftest"
        exit 1
    fi
fi

if [ "${1:-}" = "--selftest" ]; then
    t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
    mk() { # mk <name> <file> <content>
        d="$t/$1"; mkdir -p "$d"; ( cd "$d"
        command git init -q .; command git config user.email t@t; command git config user.name T
        for i in 1 2 3 4 5 6; do printf 'fn f%s() {}\n' "$i" > "f$i.rs"; done
        [ -n "${2:-}" ] && printf '%s\n' "$3" > "$2"
        command git add -A >/dev/null; command git commit -qm t ) ; }
    fail=0
    case_() { # case_ <name> <expected marker|OK>
        out=$(GATE_SELFCHECK_DONE=1 CCM_PUBLIC_GATE_CYRILLIC=1 CCM_PUBLIC_GATE_NAMES='Alice|Acme' CCM_PUBLIC_GATE_INTERNAL='AGENT-NOTES|inbox' "$0" "$t/$1" 2>&1); rc=$?
        if [ "$2" = "OK" ]; then
            [ "$rc" -eq 0 ] && echo "  ok  $1 - passed, as it should" || { echo "  BAD $1 - blocked although clean"; fail=1; }
        else
            if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "$2"; then echo "  ok  $1 - caught by the \"$2\" check"
            else echo "  BAD $1 - the \"$2\" check did NOT fire (rc=$rc)"; fail=1; fi
        fi; }
    mk cyr    ua.rs      '// comment: Привіт'
    mk name   nm.rs      '// author: Alice decided this'
    mk secret tok.txt    "K=gh$(printf p)_FAKE00000000000000000000000000000000"
    mk intern AGENT-NOTES.md 'internal swarm notes'
    mk clean  ""         ''
    mk hist   ""         ''
    ( cd "$t/hist"; printf '// Привіт\n' > old.rs; command git add -A; command git commit -qm add; command git rm -q old.rs; command git commit -qm rm )
    echo "self-test matrix:"
    case_ cyr    "CYRILLIC"
    case_ name   "NAMES"
    case_ secret "SECRETS"
    case_ intern "INTERNAL"
    case_ hist   "HISTORY"
    case_ clean  "OK"
    [ "$fail" -eq 0 ] && echo "selftest PASS - every check can fail on its own" || echo "selftest FAIL"
    exit "$fail"
fi

TARGET="${1:-}"
[ -d "$TARGET" ] || { echo "usage: public_gate.sh <snapshot dir> | --selftest" >&2; exit 2; }
cd "$TARGET" || exit 2
fail=0
say() { printf '%s\n' "$*"; }
say "=== PUBLIC GATE: $TARGET ==="
n_files=$(git ls-files 2>/dev/null | wc -l)
if [ "$n_files" -lt 5 ]; then
    say "GATE BROKEN: I see only $n_files files - nothing to check."
    say "     Usually one cause: git cannot read the repo (permissions / not a repo / empty clone)."
    exit 1
fi
say "checking $n_files files"

if [ "$CYR" = 1 ]; then
    cyr_files=$(git ls-files -z 2>/dev/null | xargs -0 grep -lIP "[\p{Cyrillic}]" 2>/dev/null | wc -l)
    if [ "$cyr_files" -gt 0 ]; then
        say "CYRILLIC: found in $cyr_files files"
        git ls-files -z | xargs -0 grep -lIP "[\p{Cyrillic}]" 2>/dev/null | head -10 | sed 's/^/     /'
        fail=1
    else say "ok: no Cyrillic"; fi
fi

if [ -n "$NAMES" ]; then
    name_hits=$(git ls-files -z 2>/dev/null | xargs -0 grep -hoIP "(?<![\p{L}])($NAMES)(?![\p{L}])" 2>/dev/null | wc -l)
    if [ "$name_hits" -gt 0 ]; then
        say "NAMES: $name_hits mentions"
        git ls-files -z | xargs -0 grep -noIP "(?<![\p{L}])($NAMES)(?![\p{L}])" 2>/dev/null | head -10 | sed 's/^/     /'
        fail=1
    else say "ok: no names"; fi
fi

# history: the whole history goes out, not only the current slice
hist_cyr=0
if [ "$CYR" = 1 ]; then
    hist_cyr=$(git rev-list --objects --all 2>/dev/null | awk '{print $1}' | sort -u \
               | git cat-file --batch 2>/dev/null | grep -acP "[\p{Cyrillic}]" || true)
fi
hist_msg=0
pat="[\p{Cyrillic}]"; [ "$CYR" = 1 ] || pat="(?!)"
[ -n "$NAMES" ] && pat="$pat|(?<![\p{L}])($NAMES)(?![\p{L}])"
hist_msg=$(git log --all --format='%an %ae%n%s%n%b' 2>/dev/null | grep -cP "$pat" || true)
if [ "${hist_cyr:-0}" -gt 0 ] || [ "${hist_msg:-0}" -gt 0 ]; then
    say "HISTORY: $hist_cyr file versions with Cyrillic, $hist_msg commit-message lines with Cyrillic/names"
    say "     (reminder: the safe way is a public repo from ONE fresh initial commit, without the old history)"
    fail=1
else say "ok: history clean"; fi

leak=$(git ls-files 2>/dev/null | grep -iE "($INTERNAL)" | head -10)
if [ -n "$leak" ]; then
    say "INTERNAL swarm files in the snapshot:"; printf '%s\n' "$leak" | sed 's/^/     /'; fail=1
else say "ok: no internal files"; fi

# secrets: patterns are assembled from parts and the scanners are excluded by name - a scanner contains its own
# patterns, so checking it with them ALWAYS fires, and a false alarm teaches people not to read real ones
P1='gh''p_|github''_pat_|sk-''ant-'
P2='BEGIN [A-Z ]*PRIVATE'' KEY'
P3='AKIA[0-9A-Z]{16}|"type":[[:space:]]*"service''_account"|private''_key_id'
sec=$(git ls-files -z 2>/dev/null | grep -zvE '(^|/)(secret-scan|public_gate\.sh|public-gate-test\.sh)$' \
      | xargs -0 grep -lIE "($P1|$P2|$P3)" 2>/dev/null | head -5)
if [ -n "$sec" ]; then say "SECRETS (possible):"; printf '%s\n' "$sec" | sed 's/^/     /'; fail=1
else say "ok: no secrets seen"; fi

say ""
if [ "$fail" -eq 0 ]; then say "CLEAN - push allowed"; else say "FOUND - PUSH FORBIDDEN"; fi
exit "$fail"
