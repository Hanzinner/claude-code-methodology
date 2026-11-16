#!/usr/bin/env bash
# memory-curation-check + curate_memory.py: clean memory -> silent; findings (orphan, broken index link, frontmatter,
# untouched for long, related names) -> one SessionStart JSON; the decay sweep names old inferred/unverified files;
# once a week only. MC=, CM= <path> test other copies. Sandbox: temp CLAUDE dir, no config file.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
MC=${MC:-$HERE/../hooks/memory-curation-check.sh}
CM=${CM:-$HERE/../scripts/curate_memory.py}
T=$(mktemp -d) && [[ -d "$T" && "$T" != / ]] || { echo "no temp dir (mktemp missing?) - refusing to run: every path below would land in /" >&2; exit 2; }
trap 'rm -rf "$T"' EXIT
export HOME=$T/home CLAUDE_METHODOLOGY_CONF=$T/none.conf CLAUDE_METHODOLOGY_DIR=$T/c
unset CLAUDE_MEMORY_DIR
M=$T/c/memory; mkdir -p "$M/episodic" "$T/c/scripts" "$HOME"
cp "$CM" "$T/c/scripts/curate_memory.py"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1 :: ${3:-}"; fi; }
mem() {  # mem <file> <type> [verified]
    printf -- '---\nname: %s\ndescription: d\nmetadata:\n  type: %s\n  source: chat\n  verified: %s\n---\nbody\n' \
        "${1%.md}" "$2" "${3:-yes}" > "$M/$1"
}
ctx() { python3 -c 'import json,sys; t=sys.stdin.read().strip(); print(json.loads(t)["hookSpecificOutput"]["additionalContext"] if t else "")'; }
run() { rm -f "$T/c/cache/memory_curation_last"; bash "$MC" | ctx; }

mem user_sam.md user; mem project_acme.md project
printf '# idx\n- [Sam](user_sam.md)\n- [Acme](project_acme.md)\n' > "$M/MEMORY.md"
o=$(run)
ok "1 clean memory -> silent" '[[ -z "$o" ]]' "$o"
mem user_sam_health.md user
o=$(run)
ok "2 a file not in MEMORY.md -> orphan" '[[ "$o" == *"orphan: user_sam_health.md"* ]]' "$o"
ok "3 same type_topic prefix -> possibly related" '[[ "$o" == *"possibly related (user_sam_*)"* ]]' "$o"
printf -- '- [Sam health](user_sam_health.md)\n- [Gone](gone.md)\n' >> "$M/MEMORY.md"
o=$(run)
ok "4 an index link to a missing file -> broken link" '[[ "$o" == *"broken link in MEMORY.md: gone.md"* ]]' "$o"
printf 'no frontmatter\n' > "$M/reference_x.md"; printf -- '- [x](reference_x.md)\n' >> "$M/MEMORY.md"
printf -- '---\nname: y\ndescription: d\nmetadata:\n  type: rumor\n---\n' > "$M/reference_y.md"; printf -- '- [y](reference_y.md)\n' >> "$M/MEMORY.md"
o=$(run)
ok "5 no frontmatter -> named" '[[ "$o" == *"no frontmatter: reference_x.md"* ]]' "$o"
ok "6 unknown type -> named" '[[ "$o" == *"unknown type '"'"'rumor'"'"'"* ]]' "$o"
mem feedback_old.md feedback inferred; printf -- '- [old](feedback_old.md)\n' >> "$M/MEMORY.md"
touch -d '45 days ago' "$M/feedback_old.md"
o=$(run)
ok "7 inferred and unchanged for 45 days -> decay sweep names it" '[[ "$o" == *"Memory decay: 1 unverified"* && "$o" == *"feedback_old.md"* ]]' "$o"
ok "8 45 days is under the stale threshold (60)" '[[ "$o" != *"untouched 45 days"* ]]' "$o"
touch -d '90 days ago' "$M/project_acme.md"
o=$(run)
ok "9 untouched 90 days -> 'still true?'" '[[ "$o" == *"untouched 90 days: project_acme.md"* ]]' "$o"
mem feedback_new.md feedback unverified
printf -- '---\nname: e\n  verified: inferred\n---\n' > "$M/episodic/2026-01.md"; touch -d '90 days ago' "$M/episodic/2026-01.md"
o=$(run); d=${o#*Memory decay}
ok "10 a fresh unverified file and episodic/ are not in the decay list" '[[ "$o" == *"Memory decay"* && "$d" != *"feedback_new.md"* && "$o" != *"2026-01.md"* ]]' "$d"
o=$(bash "$MC" | ctx)
ok "11 a second run within the week -> silent" '[[ -z "$o" ]]' "$o"
python3 -c 'import json,sys; json.loads(sys.stdin.read())' < <(rm -f "$T/c/cache/memory_curation_last"; bash "$MC") 2>/dev/null; rc=$?
ok "12 the output is one valid JSON document (report + decay together)" '[[ $rc == 0 ]]' "rc=$rc"
echo "memory-curation: $pass pass, $fail fail"; (( fail == 0 ))
