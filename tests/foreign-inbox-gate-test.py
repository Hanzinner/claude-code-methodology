#!/usr/bin/env python3
"""foreign-inbox-gate: Bash writes into inbox.md, Edit/Write on inbox.md, apostrophes in inbox_post text.
Runs the repo copy; FG=<path> tests another copy. Sandbox: temp HOME and agents dir; the hook runs as a subprocess."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
FG = os.environ.get("FG", os.path.join(HERE, "..", "hooks", "foreign-inbox-gate.py"))
T = tempfile.mkdtemp(prefix="fig-test-")
AG = f"{T}/Agents"
home = f"{T}/h"; os.makedirs(f"{home}/.claude/agent-identity"); os.makedirs(f"{AG}/Alpha"); os.makedirs(f"{AG}/Beta")
open(f"{home}/.claude/agent-identity/sidA", "w").write(f"{AG}/Alpha\n")
ENV = {**os.environ, "HOME": home, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_AGENTS_DIR": AG,
       "CCM_CLAUDE_DIR": f"{T}/inst", "HANZ_TEST": "1"}
IB = f"{AG}/Beta/inbox.md"
SC = f"{T}/inst/scripts"
P = F = 0


def run(tool, ti, sid="sidA"):
    r = subprocess.run([sys.executable, FG], input=json.dumps({"session_id": sid, "tool_name": tool, "tool_input": ti}),
                       capture_output=True, text=True, env=ENV)
    return r.stdout, r.returncode


def bash(c): return run("Bash", {"command": c})


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


def denied(o): return '"deny"' in o


BASH = [
    # writes -> deny
    (f"echo '- [ ] x' >> {IB}", 1),
    (f"printf 'x' > {IB}", 1),
    (f"echo x | tee -a {IB}", 1),
    (f"sed -i '/old/d' {IB}", 1),
    ("cd Agents/Beta && echo x >> inbox.md", 1),
    (f"python3 - <<'EOF'\nt=open('{IB}').read()\nopen('{IB}','w').write(t.replace('a','b'))\nEOF", 1),
    (f"python3 - <<'EOF'\nfrom pathlib import Path\nPath('{IB}').write_text('x')\nEOF", 1),
    (f"python3 -c \"open('{IB}','a').write('x')\"", 1),
    (f"f={IB}; echo x >> \"$f\"", 1),
    (f"python3 - <<'EOF'\np='{IB}'\ns=open(p).read()\nopen(p,'w').write(s+'x')\nEOF", 1),
    (f"sudo tee {IB} < /dev/null", 1),
    # allowed: the sanctioned tools, reads, the lock file, other targets
    (f"{SC}/inbox_post.sh Beta \"text with >> inbox.md inside\"", 0),
    (f"{SC}/inbox_done.sh Beta \"substring\"", 0),
    (f"grep -c x {IB}; cat {IB} | head", 0),
    (f"python3 - <<'EOF'\nt=open('{IB}').read()\nprint(len(t))\nEOF", 0),
    (f"python3 - <<'EOF'\nimport fcntl\nlk=open('{IB}.lock','a'); fcntl.flock(lk,fcntl.LOCK_EX)\nopen('{IB}','w').write('x')\nEOF", 0),
    (f"echo x >> {IB}.lock", 0),
    ("echo 'write to inbox.md only through inbox_post' > notes.txt", 0),
    (f"python3 - <<'EOF'\nt=open('{IB}').read()\nopen('/tmp/box.md','w').write(t)\nEOF", 0),
    (f"python3 - <<'EOF'\np='{IB}'; t=open(p).read()\nopen('/tmp/other.md','a').write(t)\nEOF", 0),
    ("git status", 0),
    # the false positive this port fixes: the file NAME appears in text, the write goes elsewhere
    ("cat > template.md <<'EOF'\nTo notify an agent append a line to inbox.md\necho x >> inbox.md\nEOF", 0),
    ("python3 - <<'EOF'\nopen('out.md','w').write('copy this template into inbox.md of the agent')\nEOF", 0),
    ("python3 - <<'EOF'\nTEMPLATE = 'Write letters to inbox.md'\nopen('/tmp/readme.txt','w').write(TEMPLATE)\nEOF", 0),
    ("python3 - <<'EOF'\nopen('notes.md','w').write(\"see inbox.md for the rules\")\nEOF", 0),
    ("python3 -c \"open('out.md','w').write('mentions inbox.md only')\"", 0),
    ("echo \"the rule: nobody does > inbox.md or >> inbox.md\" > rules.txt", 0),
    # apostrophes inside single quotes of inbox_post / inbox_done text
    (f"{SC}/inbox_post.sh Beta '- [ ] text about don't and can't'", 1),
    (f"{SC}/inbox_post.sh Beta <<<'- [ ] it didn't arrive'", 1),
    (f"{SC}/inbox_done.sh Beta 'it's done' 'ok'", 1),
    (f"{SC}/inbox_post.sh Beta '- [ ] п'ять і б'є'", 1),
    (f"{SC}/inbox_post.sh Beta \"- [ ] in double quotes don't is fine\"", 0),
    (f"{SC}/inbox_post.sh Beta <<'EOF'\n- [ ] heredoc: don't, can't, it's\nEOF", 0),
    (f"{SC}/inbox_post.sh Beta '- [ ] no apostrophe' && echo 'don't'", 1),
    ("echo 'not a letter: don't'", 0),
    (f"{SC}/inbox_post.sh Beta '- [ ] the proper escape Can'\"'\"'t is ok'", 0),
]
for c, e in BASH:
    o, rc = bash(c)
    ok(f"bash {'deny' if e else 'pass'}: {c.replace(chr(10), '⏎')[:90]}", denied(o) == bool(e) and rc == 0, o)

# Edit / Write
o, _ = run("Edit", {"file_path": IB}); ok("Edit foreign inbox -> deny, names inbox_post", denied(o) and "inbox_post.sh Beta" in o, o)
o, _ = run("Write", {"file_path": f"{AG}/Alpha/inbox.md"}); ok("Write OWN inbox -> deny, names inbox_done", denied(o) and "inbox_done.sh Alpha" in o, o)
o, _ = run("Edit", {"file_path": f"{AG}/Beta/briefing.md"}); ok("Edit another file of an agent -> allowed", o == "", o)
o, _ = run("Edit", {"file_path": f"{T}/elsewhere/inbox.md"}); ok("Edit an inbox.md OUTSIDE the agents dir -> allowed", o == "", o)
o, _ = run("Write", {"file_path": f"{AG}/Beta/inbox.md"}, sid="nobody"); ok("no identity: still a foreign inbox -> deny", denied(o), o)
o, _ = run("Read", {"file_path": IB}); ok("Read -> not our business", o == "", o)
r = subprocess.run([sys.executable, FG], input="not json", capture_output=True, text=True, env=ENV)
ok("broken stdin -> no output, fail-open under hook-safe (rc 1 with a trace)", r.stdout == "" and r.returncode in (0, 1), r)
print(f"foreign-inbox-gate: {P} pass, {F} fail"); sys.exit(1 if F else 0)
