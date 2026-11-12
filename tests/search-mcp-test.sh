#!/usr/bin/env bash
export HANZ_TEST=1
# Test of search_mcp.py (Tavily -> Exa rotation) + websearch-to-tavily.sh (WebSearch only when all are exhausted).
# No real API and no network beyond loopback: a local mock server stands in for both providers; a scenario file sets
# its answer. SM=<path> / WH=<path> test other copies. Sandbox: temp HOME, no config file.
set -u
HERE=$(dirname "$(readlink -f "$0")")
SM=${SM:-$HERE/../mcp/search_mcp.py}; WH=${WH:-$HERE/../hooks/websearch-to-tavily.sh}
T=$(mktemp -d); trap 'kill $SRV 2>/dev/null; rm -rf "$T"' EXIT
export HOME="$T/home" CLAUDE_METHODOLOGY_CONF=/nonexistent; mkdir -p "$HOME"
PORT=$((20000 + RANDOM % 20000))
cat > "$T/srv.py" <<'PY'
import json, sys, http.server
T = sys.argv[2]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        prov = self.path.strip("/")
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        open(f"{T}/hits", "a").write(prov + "\n")
        code = int(open(f"{T}/{prov}.code").read().strip())
        body = {"tavily": {"results": [{"title": "T-res", "url": "https://t.example", "content": "snippet t"}]},
                "exa": {"results": [{"title": "E-res", "url": "https://e.example", "highlights": ["snippet e"]}]}}[prov]
        if code != 200:
            body = {"detail": f"code {code}"}
        b = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PY
python3 "$T/srv.py" $PORT "$T" & SRV=$!
for i in 1 2 3 4 5 6 7 8 9 10; do (echo > /dev/tcp/127.0.0.1/$PORT) 2>/dev/null && break; sleep 0.2; done
export SEARCH_ENV="$T/env" SEARCH_STATE="$T/state.json" SEARCH_TAVILY_URL="http://127.0.0.1:$PORT/tavily" SEARCH_EXA_URL="http://127.0.0.1:$PORT/exa"
printf 'TAVILY_API_KEY=t\nEXA_API_KEY=e\n' > "$T/env"
codes() { echo "$1" > "$T/tavily.code"; echo "$2" > "$T/exa.code"; : > "$T/hits"; }
call() { printf '%s\n%s\n%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}' \
         '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
         '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search","arguments":{"query":"test","max_results":3}}}' \
         | python3 "$SM" | tail -1; }
hook() { echo '{"tool_name":"WebSearch"}' | bash "$WH" | grep -q '"deny"' && echo deny || echo allow; }
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; echo "   out=$out"; echo "   hits=$(tr '\n' ' ' < $T/hits) state=$(cat $T/state.json 2>/dev/null)"; fi; }

codes 200 200; out=$(call)
ok "1 Tavily alive -> Tavily answers, Exa untouched" 'echo "$out" | grep -q "search via tavily" && [ "$(cat $T/hits)" = tavily ]'
out=$(hook); ok "1b WebSearch denied while a provider is alive" '[ "$out" = deny ]'
codes 432 200; out=$(call)
ok "2 Tavily 432 -> the same query goes to Exa" 'echo "$out" | grep -q "search via exa" && echo "$out" | grep -q "skipped: tavily: quota"'
codes 200 200; out=$(call)
ok "3 Tavily on cooldown -> straight to Exa, Tavily not poked" 'echo "$out" | grep -q "search via exa" && [ "$(cat $T/hits)" = exa ]'
out=$(hook); ok "3b Exa alive -> WebSearch denied" '[ "$out" = deny ]'
codes 200 402; out=$(call)
ok "4 Exa 402 -> all exhausted, isError + WebSearch hint" 'echo "$out" | grep -q "\"isError\": true" && echo "$out" | grep -q "built-in WebSearch"'
out=$(hook); ok "4b all exhausted -> WebSearch ALLOWED" '[ "$out" = allow ]'
# cooldown over -> Tavily is first again
python3 -c "import json;p='$T/state.json';s=json.load(open(p));[v.update(until=0) for v in s.values()];json.dump(s,open(p,'w'))"
codes 200 200; out=$(call)
ok "5 cooldown over -> Tavily again, state cleared" 'echo "$out" | grep -q "search via tavily" && ! grep -q tavily $T/state.json'
rm -f "$T/state.json"; codes 429 200; out=$(call)
python3 -c "import json,time;s=json.load(open('$T/state.json'));assert s['tavily']['kind']=='rate' and s['tavily']['until']-time.time()<=61" 2>/dev/null; rc=$?
ok "6 429 -> short cooldown (<=60 s), query goes to Exa" '[ $rc = 0 ] && echo "$out" | grep -q "search via exa"'
rm -f "$T/state.json"; printf 'TAVILY_API_KEY=t\nEXA_API_KEY=\n' > "$T/env"; codes 432 200; out=$(call)
ok "7 no Exa key: Tavily 432 -> exhausted at once, Exa not poked" 'echo "$out" | grep -q "isError\": true" && [ "$(cat $T/hits)" = tavily ]'
out=$(hook); ok "7b no Exa key + Tavily exhausted -> WebSearch allowed" '[ "$out" = allow ]'
out=$(printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 "$SM")
ok "8 tools/list returns search with a schema" 'echo "$out" | python3 -c "import json,sys;d=json.load(sys.stdin);assert d[\"result\"][\"tools\"][0][\"name\"]==\"search\""'
echo "search-mcp: $pass pass, $fail fail"; [ $fail = 0 ]
