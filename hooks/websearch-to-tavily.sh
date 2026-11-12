#!/usr/bin/env bash
# PreToolUse hook on WebSearch: steer the agent to the rotating search tool mcp__search__search
# (Tavily -> Exa, mcp/search_mcp.py). The built-in WebSearch is the LAST resort: it is allowed only when every
# provider that has a key is on cooldown (same state file search_mcp.py maintains). No key at all -> allowed too
# (there is no alternative). Meaningful only together with the search MCP server.
# Keys: $CCM_SECRETS_DIR/search.env  (TAVILY_API_KEY=..., EXA_API_KEY=...). State: ~/.claude/search-state.json
eval "$(python3 "$(dirname "$(readlink -f "$0")")/../lib/ccm_conf.py" --shell)"
cat >/dev/null
allow=$(SEARCH_ENV="${SEARCH_ENV:-$CCM_SECRETS_DIR/search.env}" SEARCH_STATE="${SEARCH_STATE:-$HOME/.claude/search-state.json}" python3 - <<'PY' 2>/dev/null
import json, os, time
keys = {}
try:
    for l in open(os.environ["SEARCH_ENV"]).read().split("\n"):
        if "=" in l and not l.lstrip().startswith("#"):
            k, v = l.split("=", 1); keys[k.strip()] = v.strip().strip("'\"")
except OSError:
    pass
try:
    st = json.load(open(os.environ["SEARCH_STATE"]))
except Exception:
    st = {}
conf = [p for p, e in (("tavily", "TAVILY_API_KEY"), ("exa", "EXA_API_KEY")) if keys.get(e)]
live = [p for p in conf if st.get(p, {}).get("until", 0) <= time.time()]
print("yes" if not live else "no")
PY
)
[[ "$allow" == "yes" ]] && exit 0
cat <<'J'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"⛔ WebSearch is only a fallback here: use mcp__search__search (same query; find it with ToolSearch for the word search if it is not loaded). It rotates Tavily -> Exa on limits by itself. When all providers are exhausted this hook lets WebSearch through automatically; do not look for a way around it."}}
J
