#!/usr/bin/env python3
"""quota_status.py / quota_log_line.py in a sandbox: temp HOME, a LOOPBACK server plays the usage endpoint (Anthropic is
never called). Checks: real numbers win, estimate fallback, expired token = no request at all, the credentials file is
never rewritten (no refresh), error handling, per-agent shares, --out, --line, the hourly log line.
QS=<path> tests another copy."""
import http.server, json, os, subprocess, sys, tempfile, threading, time

HERE = os.path.dirname(os.path.realpath(__file__))
QS = os.environ.get("QS", os.path.join(HERE, "..", "scripts", "quota_status.py"))
LL = os.path.join(os.path.dirname(QS), "quota_log_line.py")
T = tempfile.mkdtemp(prefix="quota-test-")
P = F = 0


def ok(n, c, o=""):
    global P, F
    if c: P += 1
    else: F += 1; print("FAIL:", n, str(o)[:400])


HITS = []
BODY = {}


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        HITS.append((self.path, self.headers.get("Authorization")))
        code, body = BODY.get("v", (200, {}))
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(body).encode())
    def do_POST(self):          # a refresh would be a POST - record it, answer 500
        HITS.append(("POST " + self.path, None)); self.send_response(500); self.end_headers()
    def log_message(self, *a): pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_port}/api/oauth/usage"


def setup(name):
    home = os.path.join(T, name); os.makedirs(home + "/.claude/projects/p")
    return home


def tr(home, sid, ts_epoch, out=1000, model="claude-opus-4-8", ident=None):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts_epoch))
    with open(f"{home}/.claude/projects/p/{sid}.jsonl", "a") as f:
        f.write(json.dumps({"timestamp": ts, "message": {"model": model, "usage": {"input_tokens": 10, "output_tokens": out,
                "cache_read_input_tokens": 100, "cache_creation_input_tokens": 50}}}) + "\n")
    if ident:
        os.makedirs(home + "/.claude/agent-identity", exist_ok=True)
        open(f"{home}/.claude/agent-identity/{sid}", "w").write("/ws/Agents/" + ident)


def creds(home, expires_in_s):
    p = home + "/.claude/.credentials.json"
    json.dump({"claudeAiOauth": {"accessToken": "tok-ACCESS", "refreshToken": "tok-REFRESH",
                                 "expiresAt": int((time.time() + expires_in_s) * 1000)}}, open(p, "w"))
    return p


def run(home, *a):
    env = {**os.environ, "HOME": home, "QUOTA_USAGE_URL": URL, "HANZ_TEST": "1", "CLAUDE_METHODOLOGY_CONF": "/nonexistent"}
    for k in ("QUOTA_ROOTS", "QUOTA_IDENT", "QUOTA_CREDS", "QUOTA_CACHE", "QUOTA_REAL_STATE", "MACHINE_USAGE", "QUOTA_STATUS"):
        env.pop(k, None)
    return subprocess.run([sys.executable, QS, *a], capture_output=True, text=True, env=env, cwd=home)


def resets(mins):
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() + mins * 60))


# 1 real numbers (new `limits` shape) win over the estimate; per-agent shares; the request carries the bearer token
h = setup("real"); now = time.time()
tr(h, "sA", now - 600, 3000, ident="Alpha"); tr(h, "sB", now - 300, 1000, ident="Beta")
cp = creds(h, 3600); before = open(cp).read()
BODY["v"] = (200, {"limits": [{"kind": "session", "percent": 42.0, "resets_at": resets(120)},
                              {"kind": "weekly_all", "percent": 7.5, "resets_at": resets(5000)}]})
HITS.clear(); r = run(h, "--json"); d = json.loads(r.stdout)
ok("1a source api, session 42%, weekly 7.5%", d["source"] == "api" and d["pct"] == 42.0 and d["weekly"]["pct"] == 7.5, r.stdout + r.stderr)
ok("1b one GET with the bearer token, nothing else", len(HITS) == 1 and HITS[0][1] == "Bearer tok-ACCESS" and HITS[0][0].startswith("/api/oauth/usage"), HITS)
ok("1c credentials file untouched (never refreshed)", open(cp).read() == before)
ok("1d agents named from the identity files, shares add up", set(d["by_agent"]) == {"Alpha", "Beta"} and abs(sum(v["window_share"] for v in d["by_agent"].values()) - 100) < 0.5 and d["by_agent"]["Alpha"]["window_share"] > d["by_agent"]["Beta"]["window_share"], d["by_agent"])
ok("1e window_pct = share x real pct", abs(d["by_agent"]["Alpha"]["window_pct"] - d["by_agent"]["Alpha"]["window_share"] * 0.42) < 0.1, d["by_agent"])

# 2 EXPIRED token: no request at all, estimate fallback, the error says "expired"
h = setup("expired"); tr(h, "s1", time.time() - 100); cp = creds(h, -60); before = open(cp).read()
HITS.clear(); r = run(h, "--json"); d = json.loads(r.stdout)
ok("2a expired token -> ZERO requests (no network, no refresh)", HITS == [], HITS)
ok("2b source estimate + real_error mentions expired", d["source"] == "estimate" and "expired" in (d.get("real_error") or ""), d)
ok("2c credentials file untouched", open(cp).read() == before)

# 3 endpoint error -> estimate, error kept; no credentials at all -> estimate, no crash
h = setup("err"); tr(h, "s1", time.time() - 100); creds(h, 3600); BODY["v"] = (500, {})
r = run(h, "--json"); d = json.loads(r.stdout)
ok("3a HTTP 500 -> estimate, real_error HTTP 500", d["source"] == "estimate" and d.get("real_error") == "HTTP 500", d)
h = setup("nocreds"); tr(h, "s1", time.time() - 100)
r = run(h, "--json"); d = json.loads(r.stdout)
ok("3b no credentials file -> estimate, rc 0", r.returncode == 0 and d["source"] == "estimate", r.stderr)

# 4 the answer is cached: a second run within REAL_EVERY_S does not ask again
h = setup("cache"); tr(h, "s1", time.time() - 100); creds(h, 3600)
BODY["v"] = (200, {"five_hour": {"utilization": 10.0, "resets_at": resets(60)}, "seven_day": {"utilization": 3.0, "resets_at": resets(9000)}})
HITS.clear(); run(h, "--json"); r = run(h, "--json"); d = json.loads(r.stdout)
ok("4 older shape (five_hour/seven_day) understood; 2nd run within 5 min asks nothing", d["source"] == "api" and d["pct"] == 10.0 and len(HITS) == 1, (d, HITS))

# 5 the window already reset and no new session yet -> real 0%, not "silent"
h = setup("idle"); tr(h, "s1", time.time() - 100); creds(h, 3600)
BODY["v"] = (200, {"limits": [{"kind": "session", "percent": 55.0, "resets_at": resets(-30)}, {"kind": "weekly_all", "percent": 5.0, "resets_at": resets(5000)}]})
d = json.loads(run(h, "--json").stdout)
ok("5 stale session reading + fresh answer -> api, pct 0, session_idle", d["source"] == "api" and d["pct"] == 0.0 and d.get("session_idle"), d)

# 6 --out: file written atomically with the same JSON; --line reads it
h = setup("out"); tr(h, "s1", time.time() - 100, ident="Alpha"); creds(h, 3600)
BODY["v"] = (200, {"limits": [{"kind": "session", "percent": 20.0, "resets_at": resets(90)}, {"kind": "weekly_all", "percent": 4.0, "resets_at": resets(5000)}]})
dest = h + "/out/quota-status.json"
r = run(h, "--json", "--out", dest)
ok("6a --out writes the file, stdout empty", r.returncode == 0 and r.stdout == "" and json.load(open(dest))["pct"] == 20.0, (r.stdout, r.stderr))
env_line = subprocess.run([sys.executable, QS, "--line", "Alpha"], capture_output=True, text=True, env={**os.environ, "HOME": h, "QUOTA_STATUS": dest})
ok("6b --line: English line with session and the agent's share", "session 20%" in env_line.stdout and "you (Alpha)" in env_line.stdout, env_line.stdout)
env_none = subprocess.run([sys.executable, QS, "--line", "Alpha"], capture_output=True, text=True, env={**os.environ, "HOME": h, "QUOTA_STATUS": h + "/nope.json"})
ok("6c --line with no status file -> empty", env_none.stdout.strip() == "", env_none.stdout)

# 7 human report is English and does not crash
r = run(h)
ok("7 human report prints", r.returncode == 0 and "REAL QUOTA" in r.stdout and "weighted" in r.stdout, r.stdout + r.stderr)

# 8 the source never contains a refresh call
src = open(QS).read()
ok("8 no refresh call in the code (no refresh_token / grant_type / POST to a token endpoint)", "grant_type" not in src and "oauth/token" not in src and "refresh_token" not in src.replace("refresh token", ""), "")

# 9 hourly log line
h = setup("log")
json.dump({"data": {"weekly": {"pct": 12.5, "resets_at": "2026-11-20T00:00:00Z"}, "session": {"pct": 3.0}}}, open(h + "/.claude/quota-real.json", "w"))
for _ in range(2):
    subprocess.run([sys.executable, LL], env={**os.environ, "HOME": h, "QUOTA_REAL_STATE": h + "/.claude/quota-real.json", "QUOTA_HISTORY": h + "/hist.log"}, check=True)
ln = open(h + "/hist.log").read().splitlines()
ok("9a two runs -> two lines '<date> <time> weekly session resets'", len(ln) == 2 and ln[0].split()[2:] == ["12.5", "3.0", "2026-11-20T00:00:00Z"], ln)
r = subprocess.run([sys.executable, LL], env={**os.environ, "HOME": h + "/none", "QUOTA_HISTORY": h + "/h2.log"})
ok("9b no state -> nothing written, rc 0", r.returncode == 0 and not os.path.exists(h + "/h2.log"))

srv.shutdown()
print(f"quota-status: {P} pass, {F} fail")
sys.exit(1 if F else 0)
