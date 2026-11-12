#!/usr/bin/env python3
"""link-guard: files written in backticks / bare instead of clickable markdown links.
Runs the repo copy; LG=<path> tests another one. End to end: a fake transcript → Stop event → flag file.
Sandbox only: HOME, workspace and installed scripts dir are temp."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
LG = os.environ.get("LG", os.path.join(HERE, "..", "hooks", "link-guard.py"))
T = tempfile.mkdtemp(prefix="lg-test-")
WS, CD = f"{T}/ws", f"{T}/claude"
os.makedirs(f"{WS}/docs"); os.makedirs(f"{CD}/scripts"); os.makedirs(f"{T}/.claude")
for p in (f"{WS}/MISTAKES.md", f"{WS}/docs/SWARM-TOOLS.md", f"{CD}/scripts/inbox_post.sh", f"{CD}/scripts/link_guard_x.py"):
    open(p, "w").write("x\n")
ENV = {**os.environ, "HOME": T, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "CCM_WORKSPACE": WS, "CCM_CLAUDE_DIR": CD}
ENV.pop("LINK_ROOT", None)
SID = "linktest"
FLAG = f"{T}/.claude/link-guard-flags/{SID}"
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:300])


def stop(text):
    tp = f"{T}/t.jsonl"
    with open(tp, "w") as f:
        f.write(json.dumps({"type": "user", "message": {"content": "question"}}) + "\n")
        f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}) + "\n")
    if os.path.exists(FLAG): os.remove(FLAG)
    subprocess.run([sys.executable, LG], input=json.dumps({"session_id": SID, "transcript_path": tp}), capture_output=True, text=True, env=ENV)
    return open(FLAG).read() if os.path.exists(FLAG) else ""


out = stop(f"See `MISTAKES.md` and {CD}/scripts/link_guard_x.py")
ok("1 a backticked file and a bare absolute path → flag with both, finished text", "MISTAKES.md" in out and "link_guard_x.py" in out and "[link-guard]" in out and "Rule:" in out, out)
ok("2 markdown links → silent", stop(f"See [MISTAKES.md](MISTAKES.md) and [guard]({CD}/scripts/link_guard_x.py)") == "")
out = stop(f"The command `python3 {CD}/scripts/link_guard_x.py --x` and a block:\n```\ncat MISTAKES.md {CD}/scripts/link_guard_x.py\n```")
ok("3 a command in backticks and a code block → silent", out == "", out)
out = stop(f"Folders `docs/` and `{T}/`, a missing `nope/x.md`, `/dev/null`, `/usr/bin/python3`")
ok("4 folders, missing, /dev/null, binaries → silent", out == "", out)
out = stop("Line `MISTAKES.md:12` look")
ok("5 file:line in backticks → flag with the line", "MISTAKES.md:12" in out and "(MISTAKES.md#L12)" in out, out)
out = stop("Look at `SWARM-TOOLS.md` and `inbox_post.sh`")
ok("6 bare names (in the workspace and in the installed scripts/) → ready links",
   "[SWARM-TOOLS.md](docs/SWARM-TOOLS.md)" in out and f"[inbox_post.sh]({CD}/scripts/inbox_post.sh)" in out, out)
ok("7 a bare name that is not on disk → silent", stop("File `nosuch_file_xyz.md` is not created yet") == "")
out = stop(f"There is [inbox_post.sh]({CD}/scripts/inbox_post.sh) and\n```\nbash inbox_post.sh\n```")
ok("8 name inside [..](..) and in a code block → silent", out == "", out)
ok("9 line range → anchor #L12-L20", "(MISTAKES.md#L12-L20)" in stop("Look `MISTAKES.md:12-20`"))
os.makedirs(f"{WS}/a"); os.makedirs(f"{WS}/b")
for d in ("a", "b"): open(f"{WS}/{d}/dup.sh", "w").write("x\n")
out = stop("Look `dup.sh`")
ok("10 two files with one name → up to 3 variants", "2 matches" in out, out)
print(f"link-guard: {P} pass, {F} fail"); sys.exit(1 if F else 0)
