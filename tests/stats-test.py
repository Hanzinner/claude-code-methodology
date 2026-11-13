#!/usr/bin/env python3
"""stats_collect / stats_corrections / stats_orphan_docs / stats_adoption / stats_projects in a sandbox: temp HOME and
workspace, a FAKE claude binary (no network, no real model), letters land in a temp inbox. S=<scripts dir> tests another copy."""
import json, os, stat, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.realpath(__file__))
S = os.environ.get("S", os.path.join(HERE, "..", "scripts"))
T = tempfile.mkdtemp(prefix="stats-test-")
H, WS = T + "/home", T + "/ws"
AG = WS + "/Agents"
STATS = H + "/.claude/stats"
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:500])


def w(p, s="x", age_d=0):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(s)
    if age_d:
        t = time.time() - age_d * 86400; os.utime(p, (t, t))


FAKE = T + "/fakeclaude"
open(FAKE, "w").write('''#!/usr/bin/env python3
import json, re, sys
p = sys.stdin.read()
if "FAKE_DOWN" in __import__("os").environ: sys.exit(5)
rows = []
for m in re.finditer(r'\\{"id": "([^"]+)".*?"human message": "([^"]*)"', p):
    corr = "wrong" in m.group(2)
    rows.append({"id": m.group(1), "corr": corr, "what": "did it wrong" if corr else "", "cls": "tone" if corr else ""})
res = {"type": "result", "result": json.dumps(rows), "is_error": False, "modelUsage": {"m": {"inputTokens": 1, "outputTokens": 1, "costUSD": 0}}}
print(json.dumps([{"type": "system"}, res]))
''')
os.chmod(FAKE, 0o755)
ENV = {**os.environ, "HOME": H, "CLAUDE_METHODOLOGY_CONF": "/nonexistent", "HANZ_TEST": "1", "CCM_WORKSPACE": WS, "CCM_AGENTS_DIR": AG,
       "CCM_TIMEZONE": "UTC", "CLAUDE_BIN": FAKE, "CCM_STATS_OWNER": "Alpha", "CCM_MISTAKES": WS + "/MISTAKES.md",
       "CCM_CLAUDE_DIR": H + "/.claude", "STATS_DIR": STATS}


def run(script, *a, **extra):
    return subprocess.run([sys.executable, os.path.join(S, script), *a], capture_output=True, text=True, env={**ENV, **extra})


# ---- fixtures: one agent with a briefing/inbox, one tab-session transcript with a real human, one headless
now = time.time()
iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
w(AG + "/Alpha/briefing.md", "read plan.md; archive: notes/ - find by search\n")
w(AG + "/Alpha/agent-TODO.md", "- [ ] write the thing M·70\n- [ ] untagged chore\n")
w(AG + "/Alpha/human-TODO.md", "- [ ] human's own item\n")
w(AG + "/Alpha/inbox.md", "# inbox\n\n## New\n\n- [ ] [%s] Sender · 🖐 urgent thing\n- [ ] [%s] fresh one\n\n## Processed\n" %
  (time.strftime("%Y-%m-%d", time.localtime(now - 4 * 86400)), time.strftime("%Y-%m-%d", time.localtime(now))))
for n in ("plan.md", "lost.md", "notes/a.md"):
    w(AG + "/Alpha/" + n, "doc", age_d=10)
w(AG + "/_example-agent/briefing.md", "template")
w(AG + "/Paused/briefing.md", "x"); w(AG + "/Paused/forgotten.md", age_d=10)
w(STATS + "/paused-agents.txt", "Paused\n")
w(WS + "/MISTAKES.md", "# journal\n\n## %s · Alpha · classed one [class №1]\n**Status:** MECHANIZED\n\n## %s · Alpha · no class here\n**Status:** OPEN\n\n## 2026-01-01 · Alpha · old open\n**Status:** OPEN\n" %
  (time.strftime("%Y-%m-%d", time.localtime(now - 3 * 86400)), time.strftime("%Y-%m-%d", time.localtime(now - 2 * 86400))))
tab = H + "/.claude/projects/proj/sess1.jsonl"
os.makedirs(os.path.dirname(tab))
os.makedirs(H + "/.claude/agent-identity"); open(H + "/.claude/agent-identity/sess1", "w").write(AG + "/Alpha")
L = [{"type": "custom-title", "customTitle": "Alpha"},
     {"type": "user", "uuid": "u1", "timestamp": iso(now - 3000), "entrypoint": "cli", "message": {"content": "please build it"}},
     {"type": "assistant", "timestamp": iso(now - 2990), "requestId": "r1", "message": {"id": "m1", "model": "claude-opus-4-8", "content": [{"type": "text", "text": "built it badly"}],
      "usage": {"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 10000, "cache_creation_input_tokens": 2000}}},
     {"type": "user", "uuid": "u2", "timestamp": iso(now - 2900), "entrypoint": "cli", "message": {"content": "no, that is wrong, redo it"}},
     {"type": "user", "uuid": "u3", "timestamp": iso(now - 2800), "entrypoint": "cli", "message": {"content": "this is bullshit"}},
     {"type": "user", "uuid": "u4", "timestamp": iso(now - 2700), "entrypoint": "cli", "message": {"content": "ні, не так"}},
     {"type": "user", "uuid": "u5", "timestamp": iso(now - 2600), "entrypoint": "cli", "isMeta": True, "message": {"content": "meta, not human"}},
     {"type": "user", "uuid": "u6", "timestamp": iso(now - 2500), "entrypoint": "cli", "message": {"content": [{"type": "tool_result", "content": "x"}]}}]
open(tab, "w").write("\n".join(json.dumps(x, separators=(",", ":")) for x in L) + "\n")   # compact, as the real logs
hl = H + "/.claude/projects/proj/sess2.jsonl"       # headless: a human-looking message but no UI traces
open(hl, "w").write(json.dumps({"type": "user", "uuid": "h1", "timestamp": iso(now - 2000), "entrypoint": "sdk-cli", "message": {"content": "no, that is wrong"}}) + "\n")

# ---- stats_collect
r = run("stats_collect.py")
d = json.load(open(STATS + "/data.json")) if os.path.exists(STATS + "/data.json") else {}
ok("1a collect runs, data.json written, 2 sessions", r.returncode == 0 and d.get("sessions") == 2 and d.get("interactive_sessions") == 1, r.stdout + r.stderr)
A = d.get("agents", {})
ok("1b the tab is named Alpha (identity file), the headless one is 'background'", "Alpha" in A and "background" in A, list(A))
ok("1c English: 4 human messages in the tab (meta / tool_result / headless not counted), 1 correction, 1 swear (uk off)",
   A["Alpha"]["human_msgs"] == 4 and A["Alpha"]["corr"] == 1 and A["Alpha"]["swear"] == 1, A.get("Alpha"))
ok("1d headless messages are not the human's", A["background"]["human_msgs"] == 0, A.get("background"))
ok("1e cost computed (opus 1000 in, 500 out, 10000 read, 2000 write = ~$0.035)", any(abs(v - 0.035) < 0.001 for dd in d["cost_days"].values() for v in dd.values()), d["cost_days"])
os.remove(STATS + "/.cache.json")   # the cache stores parsed correction flags: a lexicon change needs a re-parse
r = run("stats_collect.py", CCM_LANG_EXTRA="uk")
A = json.load(open(STATS + "/data.json"))["agents"]
ok("1f CCM_LANG_EXTRA=uk also counts the Ukrainian correction", A["Alpha"]["corr"] == 2, A["Alpha"])
os.remove(STATS + "/.cache.json"); run("stats_collect.py")
r = run("stats_collect.py")
ok("1g second run uses the cache (0 re-parsed)", "(0 re-parsed)" in r.stdout, r.stdout)

# ---- stats_corrections
w(STATS + "/corrections-classes.json", json.dumps({"tone": {}, "scope": {"verdict": "one-off"}}))
r = run("stats_corrections.py", "--days", "2", "--dry")
ok("2a dry run counts the human's tab messages (4), no model call", "new: 4" in r.stdout, r.stdout + r.stderr)
r = run("stats_corrections.py", "--days", "2")
c = json.load(open(STATS + "/corrections.json")) if os.path.exists(STATS + "/corrections.json") else {}
ok("2b one correction found by the fake model, class 'tone' without a verdict = red", r.returncode == 0 and c.get("total") == 1 and c["red"] == 1 and c["classes"][0]["cls"] == "tone", r.stdout + r.stderr + str(c))
inbox = open(AG + "/Alpha/inbox.md").read()
ok("2c ONE letter to the owner about the red class", inbox.count("corrections - new corrections without a verdict") == 1 and '"tone" 1x' in inbox, inbox)
r = run("stats_corrections.py", "--days", "2")
ok("2d rerun: nothing new, no second letter", "new: 0" in r.stdout and open(AG + "/Alpha/inbox.md").read().count("corrections - new corrections") == 1, r.stdout)
w(STATS + "/corrections-classes.json", json.dumps({"tone": {"verdict": "mechanism", "since": "2000-01-01", "mech": "hook"}}))
c = None; run("stats_corrections.py", "--days", "2"); c = json.load(open(STATS + "/corrections.json"))
ok("2e a 'mechanism' that repeated AFTER its since date stays red", c["classes"][0]["red"] and c["classes"][0]["repeat_after_mech"] == 1, c["classes"])
os.remove(STATS + "/.corrections-seen.json")
r = run("stats_corrections.py", "--days", "2", FAKE_DOWN="1")
ok("2f the model is down -> rc 1 (visible failure), nothing marked seen", r.returncode == 1 and not os.path.exists(STATS + "/.corrections-seen.json"), r.stdout + r.stderr)
w(STATS + "/corrections-classes.json", "{broken")
r = run("stats_corrections.py", "--dry")
ok("2g a hand-broken registry -> rc 2 and a loud message, not a silent {}", r.returncode == 2 and "BROKEN JSON" in r.stderr, r.stderr)
r = run("stats_corrections.py", "--after", "25")
ok("2h --after later than any hour -> quiet no-op", r.returncode == 0 and r.stdout == "", r.stdout)

# ---- stats_orphan_docs
r = run("stats_orphan_docs.py", "--dry")
o = json.load(open(STATS + "/orphan-docs.json"))
orph = {x["path"] for x in o["agents"]["Alpha"]["orphans"]}
ok("3a only the uncovered doc is an orphan (plan.md named, notes/ covered by 'notes/')", orph == {"lost.md"}, orph)
ok("3b paused agent and _example are not reported, --dry sends nothing", "Paused" not in o["agents"] and "_example-agent" not in o["agents"] and "orphan_docs" not in open(AG + "/Alpha/inbox.md").read(), list(o["agents"]))
r = run("stats_orphan_docs.py")
ok("3c a real run sends ONE letter to the agent that names the file", open(AG + "/Alpha/inbox.md").read().count("orphan_docs - your folder has 1 documents") == 1 and "lost.md" in open(AG + "/Alpha/inbox.md").read(), r.stdout + r.stderr)
run("stats_orphan_docs.py")
ok("3d second run the same day: no repeat letter", open(AG + "/Alpha/inbox.md").read().count("orphan_docs - your folder") == 1)

# ---- stats_adoption
open(AG + "/Alpha/inbox.md", "w").write("# inbox\n\n## New\n\n- [ ] [%s] Sender · 🖐 urgent thing\n- [ ] [%s] fresh one\n\n## Processed\n" %
  (time.strftime("%Y-%m-%d", time.localtime(now - 4 * 86400)), time.strftime("%Y-%m-%d", time.localtime(now))))
r = run("stats_adoption.py")
a = json.load(open(STATS + "/adoption.json"))
ok("4a todo counts: 2 open, 1 tagged, the human's list not counted", a["agents"]["Alpha"]["open"] == 2 and a["agents"]["Alpha"]["tagged"] == 1, a["agents"]["Alpha"])
ok("4b inbox: 2 new, 1 older than 3 days, a stuck urgent item is red", a["agents"]["Alpha"]["inbox_new"] == 2 and a["agents"]["Alpha"]["inbox_old3"] == 1 and any("urgent item hangs" in x for x in a["red"]), a)
ok("4c journal: entries without a class and OPEN > 14 days are counted", a["summary"]["untagged"] == 1 and a["summary"]["stale_open"] == 1, a["summary"])
ok("4e one journal letter to the owner", open(AG + "/Alpha/inbox.md").read().count("the mistakes journal has unsorted entries") == 1, r.stdout)
run("stats_adoption.py")
ok("4f no second letter the same day", open(AG + "/Alpha/inbox.md").read().count("the mistakes journal has unsorted entries") == 1)

# ---- stats_projects
w(WS + "/Project-Demo/ROADMAP.md", "# Demo\n\n## North star\nBuild the demo.\n\n## EPIC 1 - Base ✅\n- ✅ **[E1.S1] first story** `M·90` · Done when: it runs\n- \U0001F504 **[E1.S2] second story** `S·50`\n- **[E1.S3] third**\n\n## EPIC 2 - Later ⏳\n")
w(WS + "/Project-Old/ROADMAP.md", "# Old\n\n## ⏸ PAUSE since 2026-09-27 - waiting\n\n## ЕПІК 1 — Старе ✅\n- ✅ **[E1.A1] old story** `S·10` · Готово коли: ok\n")
w(WS + "/Project-Bad/ROADMAP.md", "no epics here\n")
r = run("stats_projects.py")
pj = {p["name"]: p for p in json.load(open(STATS + "/projects.json"))["projects"]}
st = [s for e in pj["Demo"]["epics"] for s in e["stories"]]
ok("5a Demo: 2 epics, 3 stories, marks done/in-progress/none, size and DoD", len(pj["Demo"]["epics"]) == 2 and [s["mark"] for s in st] == ["✅", "\U0001F504", ""] and st[0]["size"] == "M·90" and st[0]["dod"] == "it runs", pj["Demo"])
ok("5b Old: pause line read, Ukrainian roadmap format still parsed", pj["Old"]["pause"].startswith("since 2026-09-27") and pj["Old"]["epics"][0]["stories"][0]["dod"] == "ok", pj["Old"])
ok("5c a roadmap without epics -> error listed, rc 1 (visible)", r.returncode == 1 and "Bad: no '## EPIC N -'" in r.stdout, r.stdout)

print(f"stats: {P} pass, {F} fail")
sys.exit(1 if F else 0)
