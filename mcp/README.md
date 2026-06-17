# MCP servers

**Model Context Protocol** is Anthropic's standard for plugging external tools and data into Claude Code. A server exposes tools that the agent can call as native (alongside `Read`/`Bash`/`Write`/etc).

This directory is documentation only — there's nothing to install from here. The setup commands below run against your local Claude Code install.

## Why MCP over a shell wrapper

- Tools appear in `/mcp` listing and the tool selector with proper schemas
- Input validation happens at the protocol layer
- Hosted servers (HTTP transport) need no local process
- Configuration is portable across sessions and projects

## Recommended starter: Tavily (web search + extraction)

Tavily replaces the built-in `WebSearch` with faster, higher-quality results plus URL extraction and crawl. Free tier: 1000 requests/month.

### Setup

1. Create a free account at [tavily.com](https://tavily.com), copy your API key.
2. Add the server:
   ```bash
   claude mcp add --transport http tavily \
     "https://mcp.tavily.com/mcp?tavilyApiKey=<YOUR_KEY>" \
     --scope user
   ```
3. Verify:
   ```bash
   claude mcp list      # should show ✓ Connected
   ```
4. In a new Claude Code session, `/mcp` lists the available tools.

### Tools provided

| Tool | What it does | When to use |
|------|--------------|-------------|
| `tavily_search` | Web search with depth/time/country filters | Default replacement for `WebSearch` |
| `tavily_extract` | Clean content from a URL (markdown/text) | Replaces `WebFetch` for noisy pages |
| `tavily_crawl` | Crawl a site with depth/regex filters | Collect many pages of one site (docs, blog archive) |
| `tavily_map` | Get site structure (URL list) | Reconnaissance before a crawl |
| `tavily_research` | Multi-source synthesis (Perplexity-style) | Hard questions needing aggregated sources (20/min limit) |

## Scopes

| Scope | Where it lives | When to use |
|-------|----------------|-------------|
| `--scope user` | `~/.claude.json` | Tools you want in every session/project |
| `--scope project` | `.mcp.json` in the project | Tools specific to one codebase |
| `--scope local` | Current workspace settings only | Throwaway/experimental |

For web search and research → `user`. For domain-specific (e.g. a GitHub MCP scoped to one repo) → `project`.

## Adding other servers

### HTTP transport (hosted, simplest)

```bash
claude mcp add --transport http <name> "<url-with-api-key>" --scope user
```

### stdio transport (local process via npx)

```bash
claude mcp add <name> --scope user -- npx -y <package-name>
# with env vars:
claude mcp add <name> --scope user --env KEY=value -- npx -y <package-name>
```

### Manual via settings

In `~/.claude.json` (user scope) or `.mcp.json` (project scope):

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

## Health checks

```bash
claude mcp list
```

Output:
- `✓ Connected` — working
- `! Needs authentication` — re-auth required (common with Google services)
- `✗ Failed` — bad key, bad URL, or network

## Security

- API keys typically live in the URL (HTTP transport) or env (stdio). Never commit them.
- Make sure your `~/.claude.json` is outside any git tree, or `.gitignore`d.
- If a key leaks, revoke at the provider dashboard and regenerate.

## Other servers worth knowing

- **Perplexity MCP** — synthesized answers ($20/mo). Step up from Tavily for hard research.
- **GitHub MCP** — PRs, issues, repos as tools.
- **Notion / Obsidian MCP** — write to vault from the agent.
- **Firecrawl MCP** — JS-rendering for SPA-heavy sites.
- **Playwright MCP** — headless browser automation.

Pick by need, not by inventory — every extra tool is more decision surface for the agent.
