#!/usr/bin/env python3
"""dashboard - a minimal, read-only status page for your agents. One file, Python standard library only.

Reads the files hooks/agent-status.py writes (~/.claude/agent-status/<agent>.json) and shows one tile per agent:
WORKING / ASK (waiting for your answer, with the question) / DONE, and how long ago it changed. Auto-refreshes.

  python3 dashboard.py [--port 8765] [--bind 127.0.0.1] [--dir ~/.claude/agent-status] [--stale-min 30]

Routes: /  (the page)   /api/status  (the same data as JSON).  Read-only: no route writes anything.
No login - it shows what your agents are doing (and any question text they typed). Keep it on localhost, or put it
behind your own reverse proxy with auth, before binding it to a network address.
A tile still saying WORKING after --stale-min minutes is shown as "stale" (the session probably died before it could say DONE).
"""
import argparse, json, os, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Agents</title>
<style>
:root{--bg:#f6f6f4;--fg:#1c1c1c;--card:#fff;--mut:#777;--work:#c77700;--ask:#b3261e;--done:#2e7d32;--stale:#999;color-scheme:light dark}
@media(prefers-color-scheme:dark){:root{--bg:#16181b;--fg:#d8d6d0;--card:#1f2226;--mut:#888;--work:#e0a030;--ask:#ff7a70;--done:#6fbf73;--stale:#777}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px system-ui,sans-serif}
h1{font-size:16px;margin:0 0 12px;font-weight:600}
#grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}
.t{background:var(--card);border-radius:8px;padding:10px 12px;border-left:5px solid var(--stale)}
.t.WORKING{border-color:var(--work)}.t.ASK{border-color:var(--ask)}.t.DONE{border-color:var(--done)}
.n{font-weight:600}.s{font-size:12px;letter-spacing:.04em}.WORKING .s{color:var(--work)}.ASK .s{color:var(--ask)}.DONE .s{color:var(--done)}
.a{font-size:12px;color:var(--mut)}.q{margin-top:6px;font-size:13px;word-break:break-word}
#e{color:var(--mut)}
</style>
<h1>Agents <span id=e></span></h1><div id=grid></div>
<script>
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ago=s=>s<60?s+' s':s<3600?Math.floor(s/60)+' min':s<86400?Math.floor(s/3600)+' h':Math.floor(s/86400)+' d';
async function go(){
  try{
    const d=await (await fetch('/api/status')).json();
    document.getElementById('e').textContent=d.agents.length?'':'- no status files yet (is hooks/agent-status.py wired?)';
    document.getElementById('grid').innerHTML=d.agents.map(a=>
      `<div class="t ${a.stale?'':a.state}"><div class=n>${esc(a.agent)}</div>`+
      `<div class=s>${a.stale?'STALE (was '+esc(a.state)+')':esc(a.state)}</div>`+
      `<div class=a>${ago(a.age_s)} ago</div>`+(a.ask?`<div class=q>${esc(a.ask)}</div>`:'')+`</div>`).join('');
  }catch(x){document.getElementById('e').textContent='- cannot reach the server'}
}
go();setInterval(go,5000);
</script>"""

ORDER = {"ASK": 0, "WORKING": 1, "DONE": 2}


def read_status(directory, stale_min, now=None):
    now = now or time.time()
    out = []
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return out
    for n in names:
        if not n.endswith(".json"):
            continue
        try:
            with open(os.path.join(directory, n), encoding="utf-8") as fh:
                d = json.load(fh)
            state = d.get("state") if d.get("state") in ORDER else "DONE"
            upd = int(d.get("updated") or 0)
        except (OSError, ValueError, TypeError):
            continue
        age = max(0, int(now - upd))
        out.append({"agent": str(d.get("agent") or n[:-5]), "state": state, "ask": str(d.get("ask") or "")[:300],
                    "updated": upd, "age_s": age, "stale": state == "WORKING" and age > stale_min * 60})
    out.sort(key=lambda a: (ORDER[a["state"]] if not a["stale"] else 3, a["agent"].lower()))
    return out


def make_handler(directory, stale_min):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/status":
                body, ctype = json.dumps({"agents": read_status(directory, stale_min)}).encode(), "application/json"
            elif path in ("/", "/index.html"):
                body, ctype = PAGE.encode(), "text/html; charset=utf-8"
            else:
                body, ctype = b"not found", "text/plain"
                self.send_response(404)
                self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store"); self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--dir", default=os.environ.get("CCM_AGENT_STATUS_DIR") or os.path.expanduser("~/.claude/agent-status"))
    ap.add_argument("--stale-min", type=int, default=30)
    ap.add_argument("--print", action="store_true", help="print the status as JSON once and exit (no server)")
    a = ap.parse_args()
    if a.print:
        print(json.dumps({"agents": read_status(a.dir, a.stale_min)}, indent=1))
        return
    print(f"dashboard: http://{a.bind}:{a.port}/  reading {a.dir}", file=sys.stderr)
    ThreadingHTTPServer((a.bind, a.port), make_handler(a.dir, a.stale_min)).serve_forever()


if __name__ == "__main__":
    main()
