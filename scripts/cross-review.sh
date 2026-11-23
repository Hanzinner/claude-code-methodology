#!/usr/bin/env bash
# cross-review.sh — independent review by a DIFFERENT model.
#
# Why: self-review by the same model is weak. On one detection-rule task the
# author model found 5 defects in its own work; other models then found ~20 more,
# and the overlap between what different models found was close to zero.
# A fresh `claude -p` never saw the code being written, so it doesn't read bugs
# charitably. See docs/coding-standard.md §2.1 (step 3 of the change cycle).
#
# Usage:
#   cross-review.sh [--model M]... [--req FILE] [--why FILE] [--repo DIR] --git <range>
#   cross-review.sh [--model M]... [--req FILE] [--why FILE] <file>...
#     --model  a model alias or full id; repeatable (each is a separate reviewer).
#              Default: sonnet. Pick a model OTHER than the one that wrote the code. A model in
#              CCM_FORBIDDEN_SUBAGENT_MODELS (the fable-gate list) is refused (rc 2) unless
#              CROSS_REVIEW_ALLOW_FORBIDDEN=1.
#     --req    a "requirement → where it's checked" table
#     --why    a "why it's like this" log, so the reviewer doesn't advise reverting
#              fixes you already paid for
#     --git    a range for `git diff` (e.g. HEAD~1..HEAD, main..feature)
# Output: one report per model in ~/.claude/cross-reviews/; the last line printed
# is the report path. The reviewer only has Read/Grep/Glob — it changes nothing.
# rc: 0 reviewed · 2 usage error / forbidden model / material too big · 3 a reviewer returned NOTHING (an empty
# answer with rc 0 looked like "no findings" — it is "no review"; run it again).
set -euo pipefail
export LC_ALL=C.UTF-8
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
forbidden=$(python3 "$HERE/../lib/ccm_conf.py" CCM_FORBIDDEN_SUBAGENT_MODELS 2>/dev/null || true)

models=(); req=""; why=""; repo="$PWD"; range=""; files=()
while (($#)); do
    case "$1" in
        --model)
            # a reviewer never runs on a model the human ruled out for subagents (cost); the critical review -> opus
            for fm in ${forbidden//,/ }; do
                if [[ "${2,,}" == *"${fm,,}"* && "${CROSS_REVIEW_ALLOW_FORBIDDEN:-0}" != 1 ]]; then
                    echo "cross-review: --model $2 refused — '$fm' is in CCM_FORBIDDEN_SUBAGENT_MODELS; take sonnet, or opus for a critical review" >&2; exit 2
                fi
            done
            models+=("$2"); shift 2 ;;
        --req)   req="$2"; shift 2 ;;
        --why)   why="$2"; shift 2 ;;
        --repo)  repo="$2"; shift 2 ;;
        --git)   range="$2"; shift 2 ;;
        -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
        *) files+=("$1"); shift ;;
    esac
done
((${#models[@]})) || models=(sonnet)
[[ -n "$range" || ${#files[@]} -gt 0 ]] || { echo "cross-review: give --git <range> or files (--help)" >&2; exit 2; }

outdir="$HOME/.claude/cross-reviews"; mkdir -p "$outdir"
ts=$(date +%Y%m%d-%H%M%S)-$$   # +PID: two runs in the same second wrote into one report, and one review was lost
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT

# ── material under review
# The fence is one backtick longer than the longest backtick run inside the content (CommonMark): otherwise a file with
# ``` inside (markdown, a heredoc) closes the block, and the reviewer reads the rest as instructions.
# A function in $(…): there `set -e` doesn't apply, so a file with no backtick at all (grep rc 1 under pipefail) still
# gets a fence — written inline in the main shell, that grep killed the whole script silently on every such file.
fence() { local n; n=$(grep -o '`\+' "$1" 2>/dev/null | awk '{ if (length($0) > m) m = length($0) } END { print m + 0 }')
          (( n < 3 )) && n=2; printf '`%.0s' $(seq $((n + 1))); }
{
    if [[ -n "$range" ]]; then
        echo "## Diff: git -C $repo diff $range"
        git -C "$repo" diff "$range" > "$work/diff.txt"
        fd=$(fence "$work/diff.txt")
        echo "${fd}diff"; cat "$work/diff.txt"; echo "$fd"
    fi
    for f in "${files[@]}"; do
        [[ -f "$f" ]] || { echo "cross-review: no such file $f" >&2; exit 2; }
        echo "## File: $(readlink -f "$f")"
        fd=$(fence "$f")
        echo "$fd"; cat "$f"; echo "$fd"
    done
} > "$work/material.md"
size=$(wc -c < "$work/material.md")
(( size < 400000 )) || { echo "cross-review: material is ${size} bytes — too big, split it" >&2; exit 2; }

{
    [[ -n "$req" ]] && { echo "## Requirements (what must hold, and where it's checked)"; cat "$req"; echo; }
    [[ -n "$why" ]] && { echo "## Why-log (deliberate decisions — don't advise reverting them without proof they're wrong)"; cat "$why"; echo; }
    true
} > "$work/context.md"

# ── the prompt gives NO hints about where to look or what counts as "minor"
prompt="You are an independent code reviewer. You did NOT see this code being written. The material is in:
- $work/material.md — the code or diff under review;
- $work/context.md — requirements and the decision log (may be empty).
File paths inside the material are real: you may read neighbouring files (Read/Grep/Glob) to check callers, siblings and context.

Task: find defects — correctness, data loss, security, races, edge cases, unmet requirements, false claims in comments.

Rules:
1. A finding counts only with PROOF: a concrete input/state → what exactly goes wrong (a repro the author can run). No repro → it's a question, list it separately.
2. For each finding: is it a one-off or a class? Name siblings of the same pattern (file:line).
3. Severity is an estimate, not a fact: give the worst realistic scenario.
4. Don't contest decisions from the why-log unless you have proof they're wrong.
5. No refactoring or style advice. Over-engineering only if the complexity itself causes a defect.
6. Your tools only read. Write each repro so the author can run it verbatim (command + expected output).

Answer format (markdown):
## Findings
### N. <one-line summary> — severity: high|medium|low
- **Where:** file:line
- **Repro:** …
- **What goes wrong:** …
- **Class / siblings:** …
- **Fix:** one or two lines
## Questions without proof
## Verdict
Exactly one line: VERDICT: PASS | FAIL | PARTIAL"

last=""; empty=0
for m in "${models[@]}"; do
    out="$outdir/$ts-$m.md"
    echo "cross-review: reviewer $m working (material ${size} bytes)…" >&2
    {
        echo "# Cross-review · model: $m · $(date '+%F %T')"
        echo "> Material: ${range:+git $range in $repo}${range:+; }${files[*]:-}"
        echo "> Requirements: ${req:-—} · Why-log: ${why:-—}"
        echo
        # --tools sets the ONLY available tools. Without it, a global allow of Bash in
        # settings.json leaks into the child session: the first run of this script
        # wrote test lines into live logs. --allowedTools only ADDS permissions.
        # claude_machine.py: no saved session per review (they cluttered the session list), spend logged as "service"
        timeout 1200 "${CROSS_REVIEW_RUNNER:-$HERE/claude_machine.py}" cross_review -p "$prompt" </dev/null --model "$m" \
            --tools "Read,Grep,Glob" --output-format text \
            || echo "⚠ claude -p exited with an error (rc=$?) — report is incomplete."
    } > "$out"
    if [[ $(sed -n '5,$p' "$out" | grep -c '[^[:space:]]') -eq 0 ]]; then
        echo "⚠ THE REVIEWER RETURNED NOTHING — this is NOT \"no findings\": no review happened. Run it again." >> "$out"
        empty=1
    fi
    # the verdict is the LAST non-empty line, as the prompt asks — a "VERDICT:" quoted mid-report doesn't count
    awk 'NF{l=$0} END{print l}' "$out" | grep -o 'VERDICT: [A-Z]*' >&2 || echo "cross-review: $m — no VERDICT line found" >&2
    last="$out"
    echo "$out"
done
if [[ $empty == 1 ]]; then exit 3; fi
exit 0
