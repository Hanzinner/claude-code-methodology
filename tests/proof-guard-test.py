#!/usr/bin/env python3
"""proof-guard v2 on synthetic transcripts: a code edit + "done" with nothing run after it -> hit (block from main());
a run after the edit / a negation / a hand-off to the human / prose only -> silent; a shared rules doc edited with
no cross-review after it -> "docs" (a flag, never a block). PG=<path> tests another copy.
Sandbox: temp HOME, no config file; the install dir, workspace and agents dir are set by CCM_* env."""
import importlib.machinery, importlib.util, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
PG = os.path.realpath(os.environ.get("PG", os.path.join(HERE, "..", "hooks", "proof-guard.py")))
T = tempfile.mkdtemp(prefix="pg-test-")
C, W = "/c/.claude", "/w"
ENV = {"HOME": f"{T}/home", "CLAUDE_METHODOLOGY_CONF": f"{T}/none.conf", "CCM_CLAUDE_DIR": C, "CCM_WORKSPACE": W,
       "CCM_AGENTS_DIR": f"{W}/Agents", "CCM_LANG_EXTRA": "uk", "CCM_HUMAN_NAME": "Sam"}
os.makedirs(ENV["HOME"])
os.environ.update(ENV)
_l = importlib.machinery.SourceFileLoader("pg", PG)   # an explicit loader: PG=…py.new (not .py) otherwise has no spec
pg = importlib.util.module_from_spec(importlib.util.spec_from_file_location("pg", PG, loader=_l)); _l.exec_module(pg)
P = F = 0


def ok(name, cond):
    global P, F
    if cond: P += 1
    else: F += 1; print("FAIL:", name)


N = [0]
def tid():
    N[0] += 1; return f"t{N[0]}"
def edit(path, lines=6):
    return ("edit", path, lines)
def bash(cmd, err=False):
    return ("bash", cmd, err)


def rows_of(steps, text):
    rows = [{"type": "user", "message": {"content": "do it"}}]
    for s in steps:
        i = tid()
        if s[0] == "edit":
            rows.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": i, "name": "Edit",
                         "input": {"file_path": s[1], "old_string": "a", "new_string": "\n" * (s[2] - 1)}}]}})
            rows.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": i, "content": "ok"}]}})
        elif s[0] == "agent":
            rows.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": i, "name": "Agent", "input": {"prompt": s[1]}}]}})
            rows.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": i, "content": "ok"}]}})
        else:
            rows.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": i, "name": "Bash", "input": {"command": s[1]}}]}})
            rows.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": i, "content": "x", "is_error": s[2]}]}})
    rows.append({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    return rows


def write(rows):
    p = f"{T}/t{tid()}.jsonl"
    open(p, "w").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return p


def turn(steps, text):
    return pg.verdict(pg.turns(write(rows_of(steps, text)))[-1])


def is_docs(v):
    return bool(v) and v[1].startswith("docs")


S = f"{C}/scripts/x.py"
ok("1 code edit + 'Done.' with no Bash -> hit", turn([edit(S)], "Done. The gate is in place."))
ok("2 edit + a run of the edited file after it -> silent", not turn([edit(S), bash(f"python3 {S} --dry")], "Done."))
ok("3 edit + only bash -n / grep -> hit", turn([edit(S), bash("bash -n x.sh"), bash("grep -n foo x.py")], "Fixed, all in place."))
ok("4 a run BEFORE the edit, nothing after -> hit", turn([bash("python3 x.py"), edit(S)], "Fixed."))
ok("5 small edit, <= 3 lines -> silent", not turn([edit(S, 2)], "Done."))
ok("6 only a .md edited -> silent", not turn([edit(f"{W}/NOTES.md")], "Done."))
ok("7 negation 'not done yet' -> silent", not turn([edit(S)], "Not done yet: waiting for the test."))
ok("8 descriptive 'works' -> silent", not turn([edit(S)], "There is a mode that works under root without the classifier."))
ok("9 'now works' as a claim -> hit", turn([edit(S)], "It now works as it should."))
ok("10 hand-off to the human ('check it on the hardware') -> silent",
   not turn([edit("/x/theme.rs")], "Done.\n\nCheck it on the hardware, whether it is readable."))
ok("10uk Ukrainian claim with CCM_LANG_EXTRA=uk -> hit", turn([edit(S)], "Готово. Гейт на місці."))
ok("10uk2 Ukrainian hand-off ('перевір на залізі') -> silent", not turn([edit("/x/theme.rs")], "Зроблено.\n\nПеревір на залізі, чи читабельно."))
py = f"python3 - <<'EOF'\np='{S}'; t=open(p).read()\nopen(p,'w').write(t)\nEOF"
ok("11 a Python heredoc writes code, then 'Done.' -> hit", turn([bash(py)], "Done."))
ok("12 write .new, test it, mv .new into place -> silent (installing what was tested)",
   not turn([bash(f"python3 - <<'EOF'\np='{S}'; open(p+'.new','w').write('1')\nEOF"),
             bash(f"PG={S}.new python3 tests/t.py"), bash(f"mv {S}.new {S}")], "Done."))
ok("13 sed -i on html after the check -> hit", turn([edit("/p/index.html"), bash("curl -s http://x"), bash("sed -i 's/a/b/' /p/index.html")], "Done."))
ok("14 claim only in a middle paragraph -> silent", not turn([edit(S)], "Started.\n\nDone part of it.\n\nNext: the test."))
ok("15 after the edit only git diff/status -> hit", turn([edit(S), bash("git -C /r diff --stat && git status")], "Done."))
ok("16 grep with | inside quotes is not a run -> hit", turn([edit(S), bash('grep -E "a|b|c" x.py | head')], "Done."))
ok("17 a .json (state) edit -> silent", not turn([edit("/x/state.json")], "Done."))
ok("17b settings.json of the install is critical -> hit", turn([edit(f"{C}/settings.json")], "Done."))
ok("18 a run by a subagent (task: run the tests) -> silent", not turn([edit(S), ("agent", "run the tests for x.py")], "Done."))
ok("18b a subagent whose task is unrelated -> hit", turn([edit(S), ("agent", "summarize the docs folder")], "Done."))

# ── shared rules documents: a rule for everyone = a critical change → a cross-review after the last edit
CS, AG = f"{W}/CODING-STANDARD.md", f"{W}/Agents/"
XR = f"{C}/scripts/cross-review.sh --model opus {CS}"
ok("19 coding standard edited + 'Done.' with no review -> docs", is_docs(turn([edit(CS)], "Done. The standard is updated.")))
ok("20 standard edited + cross-review after -> silent", not turn([edit(CS), bash(XR)], "Done."))
ok("21a review in the background via setsid nohup -> not docs",
   not is_docs(turn([edit(CS), bash("cd /x && setsid nohup " + XR + " > /tmp/o 2>&1 < /dev/null &")], "Done.")))
ok("21b nice -n 15 timeout 600 cross-review -> not docs", not is_docs(turn([edit(CS), bash("nice -n 15 timeout 600 " + XR)], "Done.")))
ok("21 cross-review BEFORE the edit -> docs", is_docs(turn([bash(XR), edit(CS)], "Done.")))
ok("22 briefings of 3 agents, 2 lines each -> docs", is_docs(turn([edit(AG + a + "/briefing.md", 2) for a in ("Kino", "Scout-Dev", "OS/OS-QA")], "Done: sent out.")))
ok("23 briefings of 2 agents -> silent", not turn([edit(AG + a + "/briefing.md", 9) for a in ("Kino", "Scout-Dev")], "Done."))
ok("24 own briefing (a recap) -> silent", not turn([edit(AG + "Tech-Dev/briefing.md", 30)], "Done: recap saved."))
ok("25 Python heredoc into ~/.claude/CLAUDE.md -> docs",
   is_docs(turn([bash("python3 - <<'EOF'\np='~/.claude/CLAUDE.md'; s=open(p).read()\nopen(p,'w').write(s)\nEOF")], "Done.")))
ok("26 LIBRARY.md / MISTAKES.md (catalog, journal) -> silent", not turn([edit(f"{W}/LIBRARY.md", 9), edit(f"{W}/MISTAKES.md", 9)], "Done."))
ok("27 small standard edit, <= 3 lines -> silent", not turn([edit(CS, 2)], "Done."))
ok("28 standard edited, no claim -> silent", not turn([edit(CS)], "Updated section 3, waiting for the archivist's view."))
ok("29 code and doc together, nothing ran -> reason is code (first)", (lambda v: bool(v) and not is_docs(v))(turn([edit(S), edit(CS)], "Done.")))
ok("30 code ran, doc not reviewed -> docs", is_docs(turn([edit(S), bash(f"python3 {S}"), edit(CS)], "Done.")))
ok("R1 standard -> review -> own briefing recap -> silent", not turn([edit(CS), bash(XR), edit(AG + "Tech-Dev/briefing.md", 30)], "Done."))
ok("R2 grep for the word cross-review is not a review -> docs", is_docs(turn([edit(CS), bash(f"grep -n cross-review {CS}")], "Done.")))
ok("R3 a failed cross-review is not a review -> docs", is_docs(turn([edit(CS), bash(XR, err=True)], "Done.")))
ok("R3b a review of ANOTHER file is not a review of the standard -> docs", is_docs(turn([edit(CS), bash(f"{C}/scripts/cross-review.sh {S}")], "Done.")))
ok("R4 sed -i with a relative path (from the workspace) -> docs", is_docs(turn([bash(f"cd {W} && sed -i 's/a/b/' CODING-STANDARD.md")], "Done.")))
ok("R5 printf > standard -> docs", is_docs(turn([bash(f"printf 'x\\n' > {CS}")], "Done.")))
ok("R6 sed on the standard && cross-review in one Bash -> silent", not turn([bash(f"sed -i 's/a/b/' {CS} && " + XR)], "Done."))
ok("R7 sed on code && a run in one Bash -> silent", not turn([bash(f"sed -i 's/a/b/' {S} && python3 {S}")], "Done."))
ok("R8 a run && then sed on code (run BEFORE the write) -> hit", bool(turn([bash(f"python3 {S} && sed -i 's/a/b/' {S}")], "Done.")))
ok("R9 relative briefings of 3 agents via sed -> docs",
   is_docs(turn([bash("sed -i 's/a/b/' Agents/Kino/briefing.md Agents/Scout-Dev/briefing.md Agents/Mercury/briefing.md")], "Done.")))
ok("R10 a comment line, then sed -i on code -> the write is seen -> hit", bool(turn([bash(f"cd /x\n# update the path\nsed -i 's/a/b/' {S}")], "Done.")))
ok("R11 heredoc writes code, print() in its body is not a run -> hit",
   bool(turn([bash(f"python3 - <<'EOF'\np='{S}'; s=open(p).read()\nopen(p,'w').write(s)\nprint('ok')\nEOF")], "Done.")))
ok("R12 heredoc writes code, then a restart in the same Bash -> silent",
   not turn([bash(f"python3 - <<'EOF'\np='{S}'; s=open(p).read()\nopen(p,'w').write(s)\nEOF\nsystemctl restart x && curl -s http://x")], "Done."))
ok("R13 sed -i on code, then only sleep -> hit", bool(turn([bash(f"sed -i 's/a/b/' {S}; sleep 1")], "Done.")))
ok("R14 after the edit only python3 -c \"import ast; ast.parse(...)\" -> hit",
   bool(turn([edit(S), bash(f"python3 -c \"import ast; ast.parse(open('{S}').read())\"")], "Done.")))
ok("R15 after the edit a module import (smoke) -> silent", not turn([edit(S), bash(".venv/bin/python -c \"import listen; print('ok')\"")], "Done."))
DM = f"{W}/DEV-METHODOLOGY.md"
XR_DM = f"{C}/scripts/cross-review.sh --model opus {DM}"
ok("R16 standard + methodology, only the standard reviewed -> docs", is_docs(turn([edit(CS), edit(DM), bash(XR)], "Done.")))
ok("R17 standard + methodology, both reviewed -> silent", not turn([edit(CS), edit(DM), bash(XR), bash(XR_DM)], "Done."))
B3 = [edit(AG + a + "/briefing.md", 2) for a in ("Kino", "Scout-Dev", "Mercury")]
ok("R18 3 briefings + a review of one briefing -> silent", not turn(B3 + [bash(f"{C}/scripts/cross-review.sh {AG}Kino/briefing.md")], "Done."))
ok("R19 3 briefings + a review of the --git diff -> silent", not turn(B3 + [bash(f"{C}/scripts/cross-review.sh --git HEAD~1..HEAD")], "Done."))
ok("R20 standard + 3 briefings, only the standard reviewed -> docs", is_docs(turn([edit(CS)] + B3 + [bash(XR)], "Done.")))
ok("R21 a custom CCM_SHARED_DOCS list is honoured", (lambda: (os.environ.update(CCM_SHARED_DOCS="/w/RULES.md"),
   pg.__dict__.update(SHARED_DOCS=pg._shared_docs()), is_docs(turn([edit("/w/RULES.md")], "Done.")))[-1])())
os.environ.pop("CCM_SHARED_DOCS"); pg.SHARED_DOCS = pg._shared_docs()


# ── main(): a block for code, a flag (never a block) for docs; the switch turns the block into a flag
def stop_event(rows, extra=None, env=None):
    tp = write(rows)
    ev = {"session_id": "pgblock", "transcript_path": tp}
    ev.update(extra or {})
    r = subprocess.run([sys.executable, PG], input=json.dumps(ev), capture_output=True, text=True,
                       env={**os.environ, **(env or {})})
    if r.returncode:
        print(r.stderr[-400:])
    return r.stdout


FLAG = f"{ENV['HOME']}/.claude/proof-guard-flags/pgblock"
out = stop_event(rows_of([edit(S)], "Done."))
ok("B1 code edit + 'Done.' with no run -> decision:block naming the file", '"decision": "block"' in out and "x.py" in out)
out = stop_event(rows_of([edit(S), bash(f"python3 {S}")], "Done."))
ok("B2 a run after the edit -> no block", out.strip() == "")
out = stop_event(rows_of([edit(S)], "Done."), {"stop_hook_active": True})
ok("B3 the stop after a block (stop_hook_active) -> no block (no loop)", out.strip() == "")
out = stop_event(rows_of([edit(CS)], "Done."))
ok("B4 a shared doc with no review -> no block, a flag with the hint", out.strip() == "" and "cross-review" in open(FLAG).read())
os.remove(FLAG)
out = stop_event(rows_of([edit(S)], "Edit made; check it on the hardware — I can't run it here."))
ok("B5 an honest hand-off ('check it on the hardware') -> no block", out.strip() == "")
out = stop_event(rows_of([edit(S)], "Done."), env={"PROOF_GUARD_BLOCK": "0"})
ok("B6 PROOF_GUARD_BLOCK=0 -> no block, a flag instead", out.strip() == "" and os.path.exists(FLAG) and "Sam" in open(FLAG).read())
conf = f"{T}/m.conf"; open(conf, "w").write("PROOF_GUARD_BLOCK=0\n")
os.remove(FLAG)
out = stop_event(rows_of([edit(S)], "Done."), env={"CLAUDE_METHODOLOGY_CONF": conf})
ok("B7 PROOF_GUARD_BLOCK=0 in methodology.conf -> no block either", out.strip() == "" and os.path.exists(FLAG))
hits = open(f"{ENV['HOME']}/.claude/proof-hits.log").read().count("\n")
ok("B8 every hit is logged (B1, B4, B6, B7 = 4)", hits == 4)

print(f"proof-guard: {P} pass, {F} fail"); sys.exit(1 if F else 0)
