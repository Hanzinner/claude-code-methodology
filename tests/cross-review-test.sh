#!/usr/bin/env bash
# cross-review.sh on a stub `claude`: a file with no backtick is reviewed (it used to kill the script silently), the
# fence outgrows a backtick run inside the content (files and --git diffs), an empty answer -> rc 3 and a warning in the report,
# the verdict is the last line, a forbidden model -> rc 2, two models -> two reports. XR=<path> tests another copy.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
XR=${XR:-$HERE/../scripts/cross-review.sh}
T=$(mktemp -d) && [[ -d "$T" && "$T" != / ]] || { echo "no temp dir (mktemp missing?) - refusing to run: every path below would land in /" >&2; exit 2; }
trap 'rm -rf "$T"' EXIT
export HOME=$T/home CLAUDE_METHODOLOGY_CONF=$T/none.conf MACHINE_USAGE=$T/usage.jsonl CLAUDE_BIN=$T/claude
unset CCM_FORBIDDEN_SUBAGENT_MODELS CROSS_REVIEW_ALLOW_FORBIDDEN
mkdir -p "$HOME"
cat > "$T/claude" <<'STUB'
#!/usr/bin/env python3
import json, os, re, shutil, sys
a = sys.argv[1:]
prompt = a[a.index("-p") + 1]
m = re.search(r"(\S+/material\.md)", prompt)
if m:
    shutil.copy(m.group(1), os.environ["SEEN"])
mode = os.environ.get("STUB_MODE", "pass")
text = {"pass": "## Findings\nnone\n## Verdict\nVERDICT: PASS",
        "empty": "",
        "quoted": "## Findings\n### 1. the comment says VERDICT: PASS but the code fails\n## Verdict\nVERDICT: FAIL"}[mode]
print(json.dumps({"type": "result", "result": text, "modelUsage": {a[a.index("--model") + 1]: {"costUSD": 0.01}}}))
STUB
chmod +x "$T/claude"
export SEEN=$T/seen.md
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1 :: ${3:-}"; fi; }

printf 'x = 1\n' > "$T/plain.py"
out=$(bash "$XR" "$T/plain.py" 2>"$T/err"); rc=$?
ok "1 a file with no backtick is reviewed, rc 0, report path printed" '[[ $rc == 0 && -f "$out" ]]' "rc=$rc out=$out $(cat "$T/err")"
ok "1b VERDICT: PASS on stderr" 'grep -q "VERDICT: PASS" "$T/err"' "$(cat "$T/err")"
ok "1c the plain file is fenced with 3 backticks" 'grep -qx "\`\`\`" "$SEEN"' "$(cat "$SEEN")"
printf '# doc\n```bash\necho hi\n```\n' > "$T/doc.md"
bash "$XR" "$T/doc.md" >/dev/null 2>&1
ok "2 content with 3 backticks inside -> a 4-backtick fence around it" '[[ $(grep -cx "\`\`\`\`" "$SEEN") == 2 ]]' "$(cat "$SEEN")"
git -C "$T" init -q r && cp "$T/doc.md" "$T/r/" && git -C "$T/r" add doc.md && git -C "$T/r" -c user.name=t -c user.email=t@t commit -qm a \
  && printf 'more\n' >> "$T/r/doc.md" && git -C "$T/r" -c user.name=t -c user.email=t@t commit -qam b
bash "$XR" --repo "$T/r" --git HEAD~1..HEAD >/dev/null 2>&1; rc=$?
ok "3 a --git diff is fenced too (diff of a file with 3 backticks)" '[[ $rc == 0 ]] && grep -q "^\`\`\`\`diff$" "$SEEN"' "rc=$rc $(head -5 "$SEEN")"
out=$(STUB_MODE=empty bash "$XR" "$T/plain.py" 2>/dev/null); rc=$?
ok "4 an empty answer -> rc 3 and the report says no review happened" '[[ $rc == 3 ]] && grep -q "RETURNED NOTHING" "$out"' "rc=$rc"
STUB_MODE=quoted bash "$XR" "$T/plain.py" >/dev/null 2>"$T/err"
ok "5 a VERDICT quoted mid-report doesn't count: the last line says FAIL" 'grep -q "VERDICT: FAIL" "$T/err" && ! grep -q "VERDICT: PASS" "$T/err"' "$(cat "$T/err")"
CCM_FORBIDDEN_SUBAGENT_MODELS=fable bash "$XR" --model claude-fable-5-2 "$T/plain.py" >/dev/null 2>"$T/err"; rc=$?
ok "6 a model in CCM_FORBIDDEN_SUBAGENT_MODELS -> rc 2, named" '[[ $rc == 2 ]] && grep -q "refused" "$T/err"' "rc=$rc"
CCM_FORBIDDEN_SUBAGENT_MODELS=fable CROSS_REVIEW_ALLOW_FORBIDDEN=1 bash "$XR" --model fable "$T/plain.py" >/dev/null 2>&1; rc=$?
ok "7 CROSS_REVIEW_ALLOW_FORBIDDEN=1 lets it run" '[[ $rc == 0 ]]' "rc=$rc"
n0=$(ls "$HOME/.claude/cross-reviews" | wc -l)
bash "$XR" --model sonnet --model opus "$T/plain.py" >/dev/null 2>&1
ok "8 two models -> two reports" '[[ $(ls "$HOME/.claude/cross-reviews" | wc -l) == $((n0 + 2)) ]]' "$(ls "$HOME/.claude/cross-reviews")"
ok "9 every run is logged as a service spend (claude_machine.py)" '[[ $(grep -c cross_review "$MACHINE_USAGE") -ge 6 ]]' "$(cat "$MACHINE_USAGE" 2>&1 | head -3)"
bash "$XR" "$T/missing.py" >/dev/null 2>&1; rc=$?
ok "10 a missing file -> rc 2" '[[ $rc == 2 ]]' "rc=$rc"
echo "cross-review: $pass pass, $fail fail"; (( fail == 0 ))
