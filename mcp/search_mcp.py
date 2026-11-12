#!/usr/bin/env python3
"""search_mcp.py - MCP server "search": ONE web-search tool that rotates providers when a limit is hit.

Queue: Tavily -> Exa. A provider that reports a limit gets a cooldown mark in a shared state file (all sessions see
it) and the same query goes to the next one - the agent does nothing. All exhausted -> the tool says "use the
built-in WebSearch", and hooks/websearch-to-tavily.sh lets WebSearch through at that moment (it reads the same state).

Limit signals: Tavily 432 = plan exhausted, 429 = rate; Exa 402 = credits, 429 = rate.
Cooldown: plan/credits - 6 h (then a trial request; a refused request costs no credit); rate - 60 s;
network/5xx - 5 min.
Keys: $CCM_SECRETS_DIR/search.env with lines TAVILY_API_KEY=... and EXA_API_KEY=... (never inside the workspace).
State: ~/.claude/search-state.json. Protocol: MCP stdio (JSON-RPC 2.0, one message per line), stdlib only.
Register:  claude mcp add --scope user search -- python3 <install dir>/mcp/search_mcp.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402
import json, time, urllib.request, urllib.error

ENV = os.environ.get("SEARCH_ENV", os.path.join(conf("CCM_SECRETS_DIR"), "search.env"))
STATE = os.environ.get("SEARCH_STATE", os.path.expanduser("~/.claude/search-state.json"))
COOLDOWN = {"quota": 6 * 3600, "rate": 60, "error": 300}
TIMEOUT = 25
# API URLs - overridable for the test only (tests/search-mcp-test.sh points them at a local mock server)
TAVILY_URL = os.environ.get("SEARCH_TAVILY_URL", "https://api.tavily.com/search")
EXA_URL = os.environ.get("SEARCH_EXA_URL", "https://api.exa.ai/search")


def load_keys():
    keys = {}
    try:
        for l in open(ENV, encoding="utf-8").read().split("\n"):
            if "=" in l and not l.lstrip().startswith("#"):
                k, v = l.split("=", 1)
                keys[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return keys


def read_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def mark(provider, kind, detail):
    st = read_state()
    st[provider] = {"until": time.time() + COOLDOWN[kind], "kind": kind, "detail": detail[:200],
                    "at": time.strftime("%F %T")}
    tmp = f"{STATE}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def clear(provider):
    st = read_state()
    if provider in st:
        st.pop(provider)
        tmp = f"{STATE}.{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
        os.replace(tmp, STATE)


class Limit(Exception):
    def __init__(self, kind, detail):
        super().__init__(detail); self.kind = kind


def post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = f"HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}"
        if e.code in (402, 432):
            raise Limit("quota", detail)
        if e.code == 429:
            raise Limit("rate", detail)
        raise Limit("error", detail)
    except Exception as e:  # network, timeout, broken JSON
        raise Limit("error", f"{type(e).__name__}: {e}")


def tavily(key, q, n):
    d = post(TAVILY_URL, {"query": q, "max_results": n},
             {"Authorization": f"Bearer {key}"})
    return [(r.get("title", ""), r.get("url", ""), r.get("content", ""), r.get("published_date", ""))
            for r in d.get("results", [])]


def exa(key, q, n):
    d = post(EXA_URL,
             {"query": q, "numResults": n, "contents": {"highlights": True, "text": {"maxCharacters": 600}}},
             {"x-api-key": key})
    out = []
    for r in d.get("results", []):
        snip = " … ".join(r.get("highlights") or []) or (r.get("text") or "")
        out.append((r.get("title") or "", r.get("url", ""), snip, r.get("publishedDate") or ""))
    return out


PROVIDERS = [("tavily", "TAVILY_API_KEY", tavily), ("exa", "EXA_API_KEY", exa)]


def available():
    """Providers that have a key and no active cooldown, in queue order."""
    keys, st, now = load_keys(), read_state(), time.time()
    return [(name, keys[env], fn) for name, env, fn in PROVIDERS
            if keys.get(env) and st.get(name, {}).get("until", 0) <= now]


def search(q, n):
    tried = []
    for name, key, fn in available():
        try:
            res = fn(key, q, n)
        except Limit as e:
            mark(name, e.kind, str(e))
            tried.append(f"{name}: {e.kind} ({e})")
            continue
        clear(name)
        lines = [f"[search via {name}" + (f"; skipped: {'; '.join(tried)}" if tried else "") + "]"]
        for i, (t, u, s, d) in enumerate(res, 1):
            s = " ".join(s.split())
            lines.append(f"{i}. {t} — {u}" + (f" ({d[:10]})" if d else "") + (f"\n   {s[:700]}" if s else ""))
        if not res:
            lines.append("(no results)")
        return "\n".join(lines), False
    why = "; ".join(tried) or "all providers are on cooldown or have no key (state: " + STATE + ")"
    return ("⛔ Search APIs exhausted (" + why + "). Use the built-in WebSearch - the hook lets it through now. "
            "Recovery is automatic after the cooldown."), True


TOOL = {"name": "search",
        "description": "Web search (Tavily -> Exa, automatic rotation on limits). Returns title, URL, "
                       "snippet, date. For the content of one page use WebFetch.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5}},
            "required": ["query"]}}


def handle(msg):
    m, mid = msg.get("method"), msg.get("id")
    if m == "initialize":
        pv = (msg.get("params") or {}).get("protocolVersion", "2025-06-18")
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": pv, "capabilities": {"tools": {}},
            "serverInfo": {"name": "search", "version": "1.0"}}}
    if m == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [TOOL]}}
    if m == "tools/call":
        a = (msg.get("params") or {}).get("arguments") or {}
        q = str(a.get("query", "")).strip()
        if not q:
            text, err = "empty query", True
        else:
            try:
                n = max(1, min(20, int(a.get("max_results", 5))))
            except (TypeError, ValueError):
                n = 5
            text, err = search(q, n)
        return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": err}}
    if m == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if mid is None:  # notification (notifications/initialized etc.) - no reply
        return None
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {m}"}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        try:
            resp = handle(msg)
        except Exception as e:
            resp = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": str(e)}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
