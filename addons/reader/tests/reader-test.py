#!/usr/bin/env python3
"""Sandboxed test of the reader: temp root and state dir, server on a free localhost port. READER=path tests another copy.
Checks what is served and what never is (outside the root, dot-files, hidden folders, other extensions), search, the
agents' section on/off, the state files, and the real entry point. Last line: reader-test: N pass, M fail."""
import importlib.util, json, os, re, shutil, subprocess, sys, tempfile, threading, time, urllib.error, urllib.parse, urllib.request
sys.dont_write_bytecode = True   # importing the server must not leave __pycache__ in the add-on folder
from http.server import ThreadingHTTPServer
from pathlib import Path

path = os.environ.get("READER") or str(Path(__file__).resolve().parent.parent / "reader-server.py")
spec = importlib.util.spec_from_file_location("reader", path); rd = importlib.util.module_from_spec(spec); spec.loader.exec_module(rd)
T = Path(tempfile.mkdtemp(prefix="reader-test-"))
passed = failed = 0


def ok(name, cond, detail=""):
    global passed, failed
    if cond: passed += 1
    else: failed += 1; print("FAIL:", name, str(detail)[:300])


R, ST, OUT = T / "root", T / "state", T / "outside"
for d in ("docs", "shared", "private", ".git", "node_modules", "Agents/Bob"):
    (R / d).mkdir(parents=True, exist_ok=True)
OUT.mkdir()
(R / "README.md").write_text("# top\nroot file")
(R / "docs/a.md").write_text("# Plan\nthe quokka line\n")
(R / "docs/b.py").write_text("print('code')")
(R / "docs/.hidden.md").write_text("dot file")
(R / ".env").write_text("KEY=secret")
(R / ".git/x.md").write_text("in git")
(R / "node_modules/n.md").write_text("quokka in modules")
(R / "private/p.md").write_text("quokka private")
(R / "Agents/Bob/briefing.md").write_text("quokka briefing")
(OUT / "o.md").write_text("outside quokka")
os.symlink(OUT / "o.md", R / "docs/link.md")
(R / "shared/old.md").write_text("old"); time.sleep(0.05); (R / "shared/new.md").write_text("new")


def serve(cfg):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), rd.make_handler(cfg))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def get(base, route, **q):
    url = base + route + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


cfg = rd.Cfg(str(R), shared="shared", hide="private", skip="briefing.md", state=str(ST))
srv, B = serve(cfg)
c, body = get(B, "/")
ok("1 page is served, own demo text (no third-party excerpt)", c == 200 and "Як користуватися читалкою" in body, c)
c, body = get(B, "/api/file", p="docs/a.md"); ok("2 a document under the root is served", c == 200 and "quokka line" in body, (c, body))
for name, p in (("3 ../ outside the root", "../outside/o.md"), ("4 absolute path outside the root", str(OUT / "o.md")),
                ("5 symlink pointing outside the root", "docs/link.md"), ("6 .env", ".env"), ("7 dot-file", "docs/.hidden.md"),
                ("8 file in .git", ".git/x.md"), ("9 file in a CCM_READER_HIDE folder", "private/p.md"),
                ("10 node_modules (always hidden)", "node_modules/n.md"), ("11 extension not on the list (.py)", "docs/b.py")):
    c, body = get(B, "/api/file", p=p); ok(name + " -> 403", c == 403, (c, body[:80]))
    c2, _ = get(B, "/api/download", p=p); ok(name + " -> download 403 too", c2 == 403, c2)
c, body = get(B, "/api/dir", p=".git"); ok("12 listing .git -> 403", c == 403, c)
c, body = get(B, "/api/dir", p="private"); ok("13 listing a hidden folder -> 403", c == 403, c)
c, body = get(B, "/api/dir", p="../outside"); ok("14 listing outside the root -> 403", c == 403, c)
d = json.loads(get(B, "/api/dir")[1])
ok("15 root listing: own folders and root files, no dot/hidden folders",
   {x["name"] for x in d["dirs"]} == {"docs", "shared", "Agents"} and [x["name"] for x in d["files"]] == ["README.md"], d)
d = json.loads(get(B, "/api/dir", p="docs")[1])
ok("16 folder listing: only reader extensions, no dot-files", [x["name"] for x in d["files"]] == ["a.md", "link.md"], d)
hits = {x["path"] for x in json.loads(get(B, "/api/search", q="quokka")[1])}
ok("17 search finds text inside a file", "docs/a.md" in hits, hits)
ok("18 search skips hidden folders, node_modules, CCM_READER_SKIP patterns, outside files",
   not hits & {"private/p.md", "node_modules/n.md", "Agents/Bob/briefing.md", "../outside/o.md"} and not any("outside" in h for h in hits), hits)
sh = json.loads(get(B, "/api/shared")[1])
ok("19 agents' section: files of CCM_READER_SHARED, newest first", [x["name"] for x in sh] == ["new.md", "old.md"], sh)
get(B, "/api/settings", set=json.dumps({"theme": "night"}))
ok("20 settings round-trip, kept in the state dir (not in the root)",
   json.loads(get(B, "/api/settings")[1]) == {"theme": "night"} and (ST / "settings.json").is_file() and not list(R.glob("*settings*")))
get(B, "/api/last", set="docs/a.md"); get(B, "/api/last", set="../outside/o.md")
ok("21 last opened: a safe path is kept, an unsafe one ignored", json.loads(get(B, "/api/last")[1]) == {"path": "docs/a.md"})
c, _ = get(B, "/api/nope"); ok("22 unknown route -> 404", c == 404, c)
srv.shutdown()

srv, B = serve(rd.Cfg(str(R), state=str(ST)))
ok("23 no CCM_READER_SHARED -> /api/shared is null (the page hides the section)", get(B, "/api/shared")[1].strip() == "null")
srv.shutdown()
ok("24 CCM_READER_SHARED outside the root -> section off", rd.Cfg(str(R), shared=str(OUT), state=str(ST)).shared is None)

# the real entry point: settings from the environment (as from methodology.conf), a free port, a warning off loopback
env = {**os.environ, "CCM_WORKSPACE": str(R), "CCM_READER_STATE": str(ST), "CLAUDE_METHODOLOGY_CONF": str(T / "none.conf")}
p = subprocess.Popen([sys.executable, path, "--port", "0"], env=env, stderr=subprocess.PIPE, text=True)
try:
    line = p.stderr.readline()
    m = re.search(r"http://127\.0\.0\.1:(\d+)/", line)
    ok("25 started from the command line: 127.0.0.1 by default, root from CCM_WORKSPACE", bool(m) and str(R) in line, line)
    if m:
        c, body = get(f"http://127.0.0.1:{m.group(1)}", "/api/file", p="docs/a.md")
        ok("26 ... and it serves", c == 200 and "quokka" in body, c)
finally:
    p.terminate(); p.wait(5)
p = subprocess.Popen([sys.executable, path, "--port", "0", "--bind", "127.0.0.2"], env=env, stderr=subprocess.PIPE, text=True)
try:
    line = p.stderr.readline()
    ok("27 a non-loopback address -> warning 'no password'", "WARNING" in line and "no password" in line, line)
finally:
    p.terminate(); p.wait(5)
r = subprocess.run([sys.executable, path, "--root", str(T / "missing"), "--port", "0"], env=env, capture_output=True, text=True, timeout=10)
ok("28 root that is not a folder -> rc 2 and a reason", r.returncode == 2 and "not a folder" in r.stderr, (r.returncode, r.stderr))

shutil.rmtree(T, ignore_errors=True)
print(f"reader-test: {passed} pass, {failed} fail")
sys.exit(1 if failed else 0)
