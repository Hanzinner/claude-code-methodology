#!/usr/bin/env python3
"""hooks/waiting-line.py in a sandbox (temp workspace, HOME, no conf file). Nothing open -> silent; blockers -> one line
with the count, the oldest first; the same session again -> silent until the set changes; another session -> shown;
human-TODO -> a count once a day; off by setting, task notices and machine sessions -> silent. WL=path tests another copy.
Last line: waiting-line-test: N pass, M fail."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WL = os.environ.get("WL") or str(REPO / "hooks" / "waiting-line.py")
T = Path(tempfile.mkdtemp(prefix="wl-test-"))
WS, HOME = T / "ws", T / "home"
(WS / "Project-Bid").mkdir(parents=True); (WS / "Project-Shop").mkdir(); (WS / "Agents" / "Bid-HQ").mkdir(parents=True)
(WS / "Agents" / "Shop-Dev").mkdir(); HOME.mkdir()
passed = failed = 0


def ok(name, cond, detail=""):
    global passed, failed
    if cond: passed += 1
    else: failed += 1; print("FAIL:", name, str(detail)[:400])


HEAD = "# BLOCKERS\n\n| No | What | Who | Check | Date | Stories |\n|---|---|---|---|---|---|\n"
def blockers(proj, rows):
    (WS / proj / "BLOCKERS.md").write_text(HEAD + "".join(f"| {i} | {w} | human | `manual` | {d} | |\n" for i, w, d in rows))


def hook(sid="s1", prompt="hi", **env):
    e = {**os.environ, "HOME": str(HOME), "CLAUDE_METHODOLOGY_CONF": str(T / "none.conf"), "CCM_WORKSPACE": str(WS),
         "CCM_AGENTS_DIR": str(WS / "Agents"), **env}
    e.pop("CCM_MACHINE_SESSION", None) if "CCM_MACHINE_SESSION" not in env else None
    r = subprocess.run([sys.executable, WL], input=json.dumps({"session_id": sid, "prompt": prompt}), capture_output=True,
                       text=True, timeout=30, env=e)
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""
    return r.returncode, ctx, r.stderr


rc, ctx, err = hook("s0")
ok("1 nothing open -> silent, rc 0", rc == 0 and ctx == "", (rc, ctx, err))
blockers("Project-Bid", [("B3", "token permissions for the payment API", "2026-11-01")])
blockers("Project-Shop", [("B1", "payment key", "2026-11-14"), ("✅ B2", "old one", "2026-10-01")])
rc, ctx, err = hook("s1")
ok("2 two open blockers (a cleared one not counted) -> one line, oldest first", rc == 0 and "waiting for you: 2 blockers" in ctx
   and ctx.index("Bid: B3") < ctx.index("Shop: B1") and "B2" not in ctx and "FIRST line" in ctx, (ctx, err))
rc, ctx, _ = hook("s1"); ok("3 same session, same blockers -> silent", ctx == "", ctx)
rc, ctx, _ = hook("s2"); ok("4 another session -> shown there too", "2 blockers" in ctx, ctx)
blockers("Project-Shop", [("B1", "payment key", "2026-11-14"), ("B4", "a domain", "2026-11-16")])
rc, ctx, _ = hook("s1"); ok("5 the set changed -> shown again in the same session", "3 blockers" in ctx and "B4" in ctx, ctx)
rc, ctx, _ = hook("s1", CCM_WAITING_REPEAT_H="0"); ok("6 repeat window passed -> shown again", "3 blockers" in ctx, ctx)

(WS / "Agents" / "Bid-HQ" / "human-TODO.md").write_text("# x\n\n## Open\n- 🎯 pick a name\n- 👁 check the page\n- [x] done one\n\n## Closed\n- old\n")
(WS / "Agents" / "Shop-Dev" / "Shop-Dev-human-TODO.md").write_text("## Open\n- 🎯 price\n## Closed\n")
rc, ctx, _ = hook("s7"); ok("7 human-TODO: count of open items and agents (closed and [x] not counted)", "in human-TODO: 3 open (2 agents)" in ctx, ctx)
rc, ctx, _ = hook("s8"); ok("8 human-TODO count only once a day (another session, same day -> no count)", "in human-TODO:" not in ctx and "blockers" in ctx, ctx)

for f in WS.glob("Project-*/BLOCKERS.md"): f.unlink()
(HOME / ".claude" / "waiting-line" / "human-todo-day").unlink()
for f in WS.glob("Agents/*/*human-TODO.md"): f.write_text("## Open\n\n## Closed\n- done\n")
rc, ctx, _ = hook("s9"); ok("9 everything closed -> silent", ctx == "", ctx)
blockers("Project-Bid", [("B3", "token", "2026-11-01")])
rc, ctx, _ = hook("s10", CCM_WAITING_LINE="0"); ok("10 CCM_WAITING_LINE=0 -> silent", ctx == "", ctx)
rc, ctx, _ = hook("s11", prompt="<task-notification> done"); ok("11 a task notice -> silent", ctx == "", ctx)
rc, ctx, _ = hook("s12", CCM_MACHINE_SESSION="1"); ok("12 a machine session -> silent", ctx == "", ctx)
rc, ctx, _ = hook("s13"); ok("13 ... and the human's next prompt in a session -> shown", "1 blocker -" in ctx, ctx)
blockers("Project-Bid", [("B3", "x" * 300, "2026-11-01")])
rc, ctx, _ = hook("s14"); ok("14 a long blocker text is cut (the line stays short)", "…" in ctx and len(ctx) < 700, len(ctx))
rc, ctx, err = hook("s15", CCM_WORKSPACE=str(T / "nope"), CCM_AGENTS_DIR=str(T / "nope")); ok("15 workspace missing -> silent, rc 0", rc == 0 and ctx == "", (rc, err))

(WS / "Agents" / "Solo").mkdir(); (WS / "BLOCKERS.md").write_text(HEAD + "| B1 | search key | human | `manual` | 2026-11-10 | Solo |\n")
rc, ctx, _ = hook("s16"); ok("16 an agent's blocker in the shared register <workspace>/BLOCKERS.md is in the line", "Solo: B1 search key" in ctx, ctx)

shutil.rmtree(T, ignore_errors=True)
print(f"waiting-line-test: {passed} pass, {failed} fail")
sys.exit(1 if failed else 0)
