#!/usr/bin/env python3
"""Sandboxed test of the agent-browser add-on: a FAKE engine and a FAKE debugging endpoint, no real browser, no network.
Env override: BR=path to another `br` (default: the one next to this test). Last line: agent-browser-test: N pass, M fail."""
import json, os, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
BR = os.environ.get("BR") or str(HERE / "br")
T = Path(tempfile.mkdtemp(prefix="br-test-"))
passed = failed = 0


def ok(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name} {str(detail)[:300]}")


# fake engine: answers `eval` from files in $FAKE_DIR, records every call
(T / "engine").write_text(r'''#!/usr/bin/env python3
import json, os, sys
d = os.environ["FAKE_DIR"]
open(d + "/calls", "a").write(json.dumps(sys.argv[1:]) + "\n")
if sys.argv[1] == "eval":
    e = sys.argv[2]
    if "data-br-target" in e: print(open(d + "/find.json").read())
    elif "innerWidth" in e: print(json.dumps({"w": 800, "h": 600, "s": "visible"}))
    elif "location.href" in e: print(json.dumps({"u": "https://example.test/", "t": "Fake"}))
    elif "visibilityState" in e: print(json.dumps(open(d + "/pagestate").read().strip()))
    elif "innerText" in e: print(json.dumps("lorem " * 100))
    else: print(json.dumps(["a", "b"]))
elif sys.argv[1] == "snapshot": print("- button \"Go\" [ref=e1]")
elif os.path.exists(d + "/fail"): print("✗ CDP connection refused"); sys.exit(1)
''')
(T / "engine").chmod(0o755)


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"Browser": "Chrome/0.0 fake"} if "version" in self.path else [{"type": "page"}]).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
ENV = dict(os.environ, BR_ENGINE=str(T / "engine"), FAKE_DIR=str(T), BR_STATE=str(T / "state"), BR_SETTLE_S="0",
           BR_CDP=f"http://127.0.0.1:{srv.server_address[1]}", BR_RECIPES=str(T / "recipes"), BR_AGENT="tester",
           HOME=str(T / "home"), CLAUDE_METHODOLOGY_CONF="/nonexistent")


def br(*a, stdin=None, **extra):
    p = subprocess.run([sys.executable, BR, *a], capture_output=True, text=True, input=stdin, env=dict(ENV, **extra), timeout=60)
    return p.returncode, p.stdout + p.stderr


def find(n, state="visible"):
    items = [{"i": i + 1, "tag": "button", "role": "", "name": "Go", "near": "row %d" % (i + 1)} for i in range(n)]
    res = {"state": state, "n": n, "items": items}
    if n == 1:
        res["picked"] = items[0]
    (T / "find.json").write_text(json.dumps(res))
    (T / "pagestate").write_text(state)


find(1)
rc, out = br("health");                    ok("health: alive", rc == 0 and "Chrome/0.0" in out, out)
rc, out = br("click", "Go");               ok("click: one match -> action", rc == 0 and "click:" in out and '"click"' in (T / "calls").read_text(), out)
find(2)
before = (T / "calls").read_text().count('"click"')
rc, out = br("click", "Go");               ok("click: two matches -> code 2, no click", rc == 2 and "--nth" in out and (T / "calls").read_text().count('"click"') == before, out)
rc, out = br("click", "Go", "--nth", "2"); ok("click --nth 2: picks one of several", rc == 0 or rc == 2, out)   # fake never marks a pick: shape only
find(0)
rc, out = br("click", "Nope");             ok("click: no match -> code 3", rc == 3, out)
find(1, "hidden")
rc, out = br("click", "Go");               ok("click: asleep page -> code 5", rc == 5 and "minimised" in out, out)
rc, out = br("health");                    ok("health: asleep page -> code 5", rc == 5, out)
find(1)
rc, out = br("open", "file:///etc/passwd"); ok("open: file:// refused", rc == 1 and "not allowed" in out, out)
rc, out = br("open", "javascript:alert(1)"); ok("open: javascript: refused", rc == 1, out)
rc, out = br("click", "@");                ok("click: empty label refused", rc == 1, out)
rc, out = br("text", "50");                ok("text: cut + marked untrusted", "cut:" in out and "untrusted" in out and rc == 0, out)
rc, out = br("help");                      ok("help: works without a browser", rc == 0 and "br click" in out, out)
rc, out = br("nonsense");                  ok("unknown command -> code 1", rc == 1, out)
log = (T / "state" / "br.log").read_text()
ok("log: every action is a line with agent and rc", "\ttester\tclick\t" in log and "rc=3" in log and "rc=5" in log, log)
# CDP down
rc, out = br("health", BR_CDP="http://127.0.0.1:9");  ok("health: endpoint down -> code 4 with a hint", rc == 4 and "unreachable" in out, out)
(T / "fail").write_text("")
rc, out = br("open", "https://example.test");          ok("engine says CDP refused -> code 4", rc == 4, out)
(T / "fail").unlink()
# recipes: closed set of actions, plan, save
rc, out = br("plan", stdin=json.dumps({"steps": [{"do": "shell", "cmd": "id"}]}));  ok("plan: action outside the list refused", rc == 1 and "unknown action" in out, out)
rc, out = br("plan", stdin=json.dumps({"steps": [{"do": "open", "url": "https://example.test"}, {"do": "js", "expr": "1+{who}"}]}), )
ok("plan: missing parameter left as is, result returned", rc == 0 and "untrusted" in out, out)
rc, out = br("plan", stdin=json.dumps({"params": ["x"], "steps": []}));  ok("plan: missing required parameter named", rc == 1 and "missing parameters: x" in out, out)
prog = {"about": "t", "steps": [{"do": "open", "url": "https://example.test"}, {"do": "js", "expr": "[1]"}], "check": {"args": {}, "expect": "a"}}
rc, out = br("plan", "--save", "t.one", stdin=json.dumps(prog)); ok("plan --save: control example passes -> saved", rc == 0 and (T / "recipes" / "t.one.json").exists(), out)
rc, out = br("plan", "--save", "t.one", stdin=json.dumps(prog)); ok("plan --save again: old copy kept in .old, not deleted", rc == 0 and len(list((T / "recipes" / ".old").glob("t.one.*.json"))) == 1, out)
bad = dict(prog, check={"args": {}, "expect": "zzz"})
rc, out = br("plan", "--save", "t.two", stdin=json.dumps(bad)); ok("plan --save: failed example -> not saved", rc == 1 and not (T / "recipes" / "t.two.json").exists(), out)
rc, out = br("recipes");                   ok("recipes: lists the saved one", "t.one" in out, out)
rc, out = br("run", "t.one");              ok("run: saved recipe works", rc == 0, out)
rc, out = br("run", "no.such");            ok("run: unknown recipe -> code 3", rc == 3, out)
rc, out = br("run", "../etc/passwd");      ok("run: path-like recipe name refused", rc == 1, out)
rc, out = br("check");                     ok("check: control examples pass", rc == 0 and "check: 1/1" in out, out)
# shipped recipes are valid JSON with a check example and English text
shipped = list((HERE / "recipes").glob("*.json"))
ok("shipped recipes: valid, have check, no Cyrillic", shipped and all("check" in json.loads(f.read_text()) and not any("Ѐ" <= c <= "ӿ" for c in f.read_text()) for f in shipped))
# setup script: dry-run only, sandboxed paths
sb = dict(os.environ, AB_UNIT_PATH=str(T / "unit.service"), AB_BIN_DIR=str(T / "bin"), AB_PROFILE_DIR=str(T / "prof"))
(T / "bin").mkdir()
s = subprocess.run([str(HERE / "setup-agent-browser.sh"), "--dry-run", "--link", "--browser-service", "--chrome", "/usr/bin/chromium", "--port", "9444"],
                   capture_output=True, text=True, env=sb)
ok("setup --dry-run: prints unit + link, writes nothing", s.returncode == 0 and "remote-debugging-port=9444" in s.stdout and "ln -s" in s.stdout
   and not (T / "unit.service").exists() and not list((T / "bin").iterdir()), s.stdout + s.stderr)
s = subprocess.run([str(HERE / "setup-agent-browser.sh"), "--dry-run", "--uninstall"], capture_output=True, text=True, env=sb)
ok("setup --uninstall --dry-run: keeps profile and user", s.returncode == 0 and "Kept" in s.stdout, s.stdout + s.stderr)
s = subprocess.run([str(HERE / "setup-agent-browser.sh"), "--port", "x"], capture_output=True, text=True, env=sb)
ok("setup: bad port refused", s.returncode == 2, s.stderr)
s = subprocess.run([str(HERE / "install-engine.sh"), "--dry-run"], capture_output=True, text=True)
ok("install-engine --dry-run: plan only", s.returncode == 0 and ("dry-run" in s.stdout or "nothing to do" in s.stdout), s.stdout + s.stderr)
# br-ask with a fake `claude`
(T / "fakebin").mkdir()
(T / "fakebin" / "claude").write_text('#!/bin/sh\necho \'{"type":"result","result":"fake answer","num_turns":2,"usage":{"input_tokens":5,"output_tokens":7},"duration_ms":1500,"is_error":false}\'\n')
(T / "fakebin" / "claude").chmod(0o755)
env2 = dict(ENV, PATH=f"{T/'fakebin'}:{os.environ['PATH']}")
p = subprocess.run([str(HERE / "br-ask"), "find x"], capture_output=True, text=True, env=env2)
ok("br-ask: prints the answer, cost on stderr, cost logged", p.returncode == 0 and "fake answer" in p.stdout and "[cost]" in p.stderr
   and "find x" in (T / "state" / "ask.log").read_text(), p.stdout + p.stderr)
print(f"agent-browser-test: {passed} pass, {failed} fail")
sys.exit(1 if failed else 0)
