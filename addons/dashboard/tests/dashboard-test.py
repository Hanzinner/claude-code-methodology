#!/usr/bin/env python3
"""Sandboxed test of the dashboard: temp status dir, server on a random localhost port, no network beyond loopback.
Env DASH=path tests another copy. Last line: dashboard-test: N pass, M fail."""
import importlib.util, json, os, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

path = os.environ.get("DASH") or str(Path(__file__).resolve().parent.parent / "dashboard.py")
spec = importlib.util.spec_from_file_location("dash", path); dash = importlib.util.module_from_spec(spec); spec.loader.exec_module(dash)
T = Path(tempfile.mkdtemp(prefix="dash-test-"))
passed = failed = 0


def ok(name, cond, detail=""):
    global passed, failed
    if cond: passed += 1
    else: failed += 1; print("FAIL:", name, str(detail)[:300])


def put(name, state, age, ask="", raw=None):
    (T / f"{name}.json").write_text(raw if raw is not None else json.dumps(
        {"agent": name, "state": state, "ask": ask, "session": "s", "updated": int(time.time()) - age}))


put("alpha", "WORKING", 10); put("bravo", "ASK", 60, "Which database <b>should</b> I use?"); put("charlie", "DONE", 7200)
put("delta", "WORKING", 40 * 60)                       # stale
put("broken", "", 0, raw="{not json")                  # must be skipped, not crash
(T / "notes.txt").write_text("ignored")
st = dash.read_status(str(T), 30)
by = {a["agent"]: a for a in st}
ok("reads 4 valid files, skips broken json and non-json", set(by) == {"alpha", "bravo", "charlie", "delta"}, list(by))
ok("ASK sorts first, then WORKING, DONE, stale last", [a["agent"] for a in st] == ["bravo", "alpha", "charlie", "delta"], [a["agent"] for a in st])
ok("a WORKING tile older than --stale-min is flagged stale", by["delta"]["stale"] and not by["alpha"]["stale"])
ok("a DONE tile is never stale however old", not by["charlie"]["stale"])
ok("ask text is carried", "Which database" in by["bravo"]["ask"])
ok("missing directory -> empty list, no crash", dash.read_status(str(T / "nope"), 30) == [])
put("weird", "EXPLODING", 5); ok("unknown state is shown as DONE", {a["agent"]: a for a in dash.read_status(str(T), 30)}["weird"]["state"] == "DONE")
(T / "weird.json").unlink()

srv = ThreadingHTTPServer(("127.0.0.1", 0), dash.make_handler(str(T), 30)); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}"
r = urllib.request.urlopen(base + "/api/status"); data = json.load(r)
ok("/api/status serves the JSON", r.status == 200 and len(data["agents"]) == 4 and r.headers["Cache-Control"] == "no-store")
page = urllib.request.urlopen(base + "/").read().decode()
ok("/ serves the page, which escapes agent text before inserting it", "<title>Agents</title>" in page and "esc(a.ask)" in page and "esc(a.agent)" in page)
try:
    urllib.request.urlopen(base + "/etc/passwd"); code = 200
except urllib.error.HTTPError as e:
    code = e.code
ok("unknown route -> 404 (no file serving)", code == 404)
req = urllib.request.Request(base + "/api/status", data=b"x", method="POST")
try:
    urllib.request.urlopen(req); code = 200
except urllib.error.HTTPError as e:
    code = e.code
ok("POST is not accepted (read-only)", code == 501, code)
srv.shutdown()
p = subprocess.run([sys.executable, path, "--print", "--dir", str(T)], capture_output=True, text=True)
ok("--print dumps JSON and exits", p.returncode == 0 and json.loads(p.stdout)["agents"][0]["agent"] == "bravo", p.stdout + p.stderr)
ok("default bind is localhost", "default='127.0.0.1'" in open(path).read().replace('"', "'") or 'default="127.0.0.1"' in open(path).read())
print(f"dashboard-test: {passed} pass, {failed} fail")
sys.exit(1 if failed else 0)
