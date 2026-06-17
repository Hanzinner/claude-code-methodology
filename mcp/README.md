# MCP servers

MCP (Model Context Protocol) is how Claude Code plugs external tools and data into the agent as native tools. Nothing to install from this directory — these are setup notes.

## Tavily (web search + extraction)

Free tier: 1000 requests/month. Sign up at https://tavily.com, copy API key.

```bash
claude mcp add --transport http tavily \
  "https://mcp.tavily.com/mcp?tavilyApiKey=<YOUR_KEY>" \
  --scope user
claude mcp list   # should show ✓ Connected
```

In a session, `/mcp` lists tools.

| Tool | Action |
|------|--------|
| `tavily_search` | Web search with depth/time/country filters |
| `tavily_extract` | Clean content from a URL (markdown/text) |
| `tavily_crawl` | Crawl a site with depth/regex filters |
| `tavily_map` | Site structure (URL list) |
| `tavily_research` | Multi-source synthesis (20/min) |

## Adding other servers

```bash
# HTTP transport (hosted)
claude mcp add --transport http <name> "<url>" --scope user

# stdio transport (local process)
claude mcp add <name> --scope user -- npx -y <package>
claude mcp add <name> --scope user --env KEY=value -- npx -y <package>
```

Manual config in `~/.claude.json` (user) or `.mcp.json` (project):

```json
{
  "mcpServers": {
    "<name>": {
      "command": "npx",
      "args": ["-y", "<package>"],
      "env": { "API_KEY": "..." }
    }
  }
}
```

## Scopes

| Scope | Location | Use |
|-------|----------|-----|
| `--scope user` | `~/.claude.json` | Every session/project |
| `--scope project` | `.mcp.json` in project | One codebase |
| `--scope local` | Workspace settings | Throwaway |

## Health

```bash
claude mcp list
```

`✓ Connected` / `! Needs authentication` / `✗ Failed`.

## Security

API keys live in URLs (HTTP) or env (stdio). Don't commit `~/.claude.json`. Revoke at provider dashboard if leaked.
