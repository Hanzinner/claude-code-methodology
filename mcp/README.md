# MCP servers

MCP (Model Context Protocol) is how Claude Code plugs external tools into the agent as native tools.
`install.sh` copies the server below into `~/.claude/mcp/`; registering it with Claude Code is one command.

## `search` — web search that rotates providers (`search_mcp.py`)

One tool, `mcp__search__search`, backed by **Tavily, then Exa**. When a provider reports a limit (plan used up,
rate limit, credits gone), it gets a cooldown in `~/.claude/search-state.json` that every session sees, and the
same query goes to the next provider — the agent does nothing. When all are exhausted, the tool says so and the
built-in `WebSearch` is let through (`hooks/websearch-to-tavily.sh` reads the same state). Python standard
library only, no packages.

**1. Keys** — either one is enough, both give the rotation. Free tiers: Tavily (https://tavily.com,
1000 searches a month), Exa (https://exa.ai, free credits on sign-up). Put them into `search.env` in your
secrets folder (`CCM_SECRETS_DIR` in `methodology.conf`, default `~/.config/claude-secrets/`), never into the
workspace:

```bash
mkdir -p ~/.config/claude-secrets && chmod 700 ~/.config/claude-secrets
cat > ~/.config/claude-secrets/search.env <<'EOF'
TAVILY_API_KEY=tvly-...
EXA_API_KEY=...
EOF
chmod 600 ~/.config/claude-secrets/search.env
```

**2. Register the server** (once, for all your projects):

```bash
claude mcp add --scope user search -- python3 ~/.claude/mcp/search_mcp.py
claude mcp list        # search: ✓ Connected
```

Restart Claude Code; `/mcp` in a session lists the tool.

**Do both steps or neither.** With a key in `search.env`, `hooks/websearch-to-tavily.sh` refuses the built-in
`WebSearch` and points the agent at `mcp__search__search`. If the server is not registered, the agent then has no
search at all. No keys → the hook lets `WebSearch` through and nothing changes.

Test without spending credits: `tests/search-mcp-test.sh` (runs against a local mock of both APIs).

## Adding other servers

```bash
# HTTP transport (hosted)
claude mcp add --transport http <name> "<url>" --scope user

# stdio transport (local process)
claude mcp add <name> --scope user -- <command> [args...]
claude mcp add <name> --scope user --env KEY=value -- <command> [args...]
```

## Scopes

| Scope | Location | Use |
|-------|----------|-----|
| `--scope local` (default) | `~/.claude.json`, under this project's path | This project, only you |
| `--scope project` | `.mcp.json` in project root | This project, shared with the team via version control |
| `--scope user` | `~/.claude.json` | All your projects |

## Health

`claude mcp list` → `✓ Connected` / `! Needs authentication` / `✗ Failed`.

## Security

Keys live in the secrets folder (mode 600), never in the workspace or in a URL that ends up in `~/.claude.json`.
Don't commit `~/.claude.json`. Revoke a key at the provider if it leaked.
