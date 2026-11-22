#!/usr/bin/env python3
"""letter-proof-hint: a result number in a letter that is not in the tool output → a hint; proven or not-a-claim → silent.
Runs against the repo copy; LP=<path> tests another one. Sandbox only: synthetic transcripts and HOME in a temp dir."""
import atexit, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
LP = os.environ.get("LP", os.path.join(HERE, "..", "hooks", "letter-proof-hint.py"))
T = tempfile.mkdtemp(prefix="lp-test-")
atexit.register(shutil.rmtree, T, True)
os.makedirs(f"{T}/home/.claude")
ENV = {**os.environ, "HOME": f"{T}/home", "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_TEST": "1", "CCM_LANG_EXTRA": ""}
P = F = 0
N = [0]


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


def run(outputs, letter=None, tool="Bash", heredoc=False, attach=None, own_text=None, lang=""):
    """outputs - tool_result texts; letter - the letter. → additionalContext ('' = silent)."""
    N[0] += 1
    rows = [{"type": "user", "message": {"content": "go"}}]
    for i, o in enumerate(outputs):
        rows.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"b{i}", "name": "Bash", "input": {"command": "x"}}]}})
        rows.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"b{i}", "content": o}]}})
    if attach:
        rows.append({"type": "attachment", "attachment": {"type": "hook_additional_context", "content": [attach]}})
    if own_text:
        rows.append({"type": "assistant", "message": {"content": [{"type": "text", "text": own_text}]}})
    tp = f"{T}/t{N[0]}.jsonl"
    open(tp, "w").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    if tool == "Bash":
        cmd = (f"~/.claude/scripts/inbox_post.sh Lead <<'EOF'\n{letter}\nEOF" if heredoc
               else f"~/.claude/scripts/inbox_post.sh Lead \"Dev\" {json.dumps(letter, ensure_ascii=False)} 2>&1 | tail -1")
        ti = {"command": cmd}
    else:
        ti = {"to": "X", "message": letter}
    ev = {"session_id": f"s{N[0]}", "tool_name": tool, "tool_input": ti, "transcript_path": tp}
    r = subprocess.run([sys.executable, LP], input=json.dumps(ev), capture_output=True, text=True,
                       env={**ENV, "CCM_LANG_EXTRA": lang})
    if r.returncode:
        print(r.stderr[-300:])
    try:
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
    except (ValueError, KeyError):
        return f"[bad output] {r.stdout[:200]}"


ok("1 'tests 21/21', output 20 pass, 0 fail → hint with the number", "21/21" in run(["unit: 20 pass, 0 fail"], "tests 21/21 green"))
ok("2 'tests 21/21', output 21 pass, 0 fail → silent", run(["unit: 21 pass, 0 fail"], "tests 21/21 green") == "")
ok("3 '11/11 pages PASS', output 'pages not PASS: 0 of 11' → silent", run(["== pages not PASS: 0 of 11"], "check_layout: 11/11 pages PASS") == "")
ok("4 '6/6', output 5/5 → hint", "6/6" in run(["Ran 5 tests\nOK\nresult 5/5"], "test 6/6, ready to merge"))
ok("5 '74 pass', output '74 pass, 0 fail' → silent", run(["x: 74 pass, 0 fail"], "all green: 74 pass") == "")
ok("6 '74 pass', output has 73 → hint", "74 pass" in run(["x: 73 pass, 1 fail"], "all green: 74 pass"))
ok("7 rc in a letter is not a claim → silent", run(["nothing"], "rc 3 means it could not measure; rc=0 as always") == "")
ok("8 widths 390/1440 next to 'checks' → silent", run(["nothing"], "width checks 390/1440 passed") == "")
ok("9 HTTP 200/405 → silent", run(["nothing"], "public paths answer 200/405 as now, no test needed") == "")
ok("10 someone else's number in quotes → silent", run(["nothing"], "QA writes “tests 47/47”, I did not run them") == "")
ok("11 retold: the number came as a letter via a hook (attachment) → silent",
   run(["nothing"], "QA PASS 114/114 → roll it to test", attach="📥 QA: QA PASS 114/114 on the stand") == "")
ok("12 SendMessage '6/6 tests', output 5/5 → hint", "6/6" in run(["5/5 tests ok"], "6/6 tests, have a look", tool="SendMessage"))
ok("13 letter in a heredoc 'test 6/6', output 5 pass → hint", "6/6" in run(["5 pass, 0 fail"], "test 6/6", heredoc=True))
ok("14 the agent's own number in its text is no proof → hint", "9/9" in run(["nothing here"], "test 9/9", own_text="Done: test 9/9"))
ok("15 decision numbers 0026/0027 → silent", run(["nothing"], "check decisions 0026/0027 and the test") == "")
ok("16 '3 failed' while the output says 2 failed → hint", "3 failed" in run(["result: 10 passed, 2 failed"], "3 failed, fixing"))
ok("17 letter with no result claim → silent", run(["nothing"], "please review the branch when you can") == "")
# Ukrainian lexicon: off by default, on with CCM_LANG_EXTRA=uk
ok("18 Ukrainian 'тест 21/21 зелений', output 20 pass, no uk → silent (Ukrainian words not matched)",
   run(["unit: 20 pass, 0 fail"], "тест 21/21 зелений") == "")
ok("19 the same with CCM_LANG_EXTRA=uk → hint", "21/21" in run(["unit: 20 pass, 0 fail"], "тест 21/21 зелений", lang="uk"))
ok("20 uk: '11/11 сторінок PASS', output 'сторінок не-PASS: 0 з 11' → silent",
   run(["== сторінок не-PASS: 0 з 11"], "check_layout: 11/11 сторінок PASS", lang="uk") == "")
ok("21 uk: '5 зелених', output '4 зелених' → hint", "5 зелених" in run(["тести: 4 зелених, 1 червоних"], "усе: 5 зелених", lang="uk"))
ok("22 uk: ширини 390/1440 біля «перевірок» → silent", run(["nothing"], "перевірка ширин 390/1440 пройдена", lang="uk") == "")
ev = {"session_id": "s", "tool_name": "Bash", "tool_input": {"command": "ls /tmp"}, "transcript_path": "/nonexistent"}
r = subprocess.run([sys.executable, LP], input=json.dumps(ev), capture_output=True, text=True, env=ENV)
ok("23 not a letter → silent, rc 0", r.stdout == "" and r.returncode == 0, r.stderr)
try:
    log = open(f"{T}/home/.claude/letter-proof-hits.log").read()
except OSError:
    log = ""
ok("24 every hint leaves a log line (cases 1,4,6,12,13,14,16,19,21 = 9)", log.count("\n") == 9, log)
print(f"letter-proof-hint: {P} pass, {F} fail")
sys.exit(1 if F else 0)
