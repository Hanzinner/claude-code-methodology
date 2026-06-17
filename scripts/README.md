# Scripts

Reusable utilities the agent (and you) can call. Most are idempotent and safe to re-run.

All scripts resolve their install location via `$CLAUDE_METHODOLOGY_DIR` (set by `install.sh`), falling back to `~/.claude`.

## Document extraction

| Script | What it does |
|--------|--------------|
| `pdf-extract.sh <pdf> [--images] [--dpi=N]` | PDF → `.txt` (full) + `.meta.txt` + `.pages/p####.txt` (per-page) + optional `.images/p####.png`. Idempotent. Auto-triggered by the `auto-extract-docs` hook. |
| `html-extract.sh <html>` | HTML → clean `.txt` via lynx (no tags/CSS/nav). For plain reading. |
| `html-to-md.sh <html>` | HTML → `.md` via pandoc (GFM, preserves headings/lists/tables/links). Use when structure matters. |

System deps: `poppler-utils` (pdftotext, pdftoppm, pdfinfo), `lynx`, `pandoc`.

## Location / geo

| Script | What it does |
|--------|--------------|
| `osm-nearby.sh <lat> <lng> [radius_km] [amenity] [name_regex]` | Find amenities near a coordinate via OSM Overpass API. Free, no signup. |

## Cross-agent dial

| Script | What it does |
|--------|--------------|
| `register_agent.py <name>` | Self-register the current Claude Code session as `<name>` in the shared registry. |
| `call_agent.sh <name> "<prompt>"` | Resume `<name>`'s session, ask the prompt, return the response. Expensive (cache miss per call). |

Both are wrapped by the `/register-as` and `/call-agent` skills — prefer those at runtime.

The registry lives at `$CLAUDE_METHODOLOGY_DIR/agent-registry.json`.

## Memory & persistence

| Script | What it does |
|--------|--------------|
| `backup-chats.sh` | Daily backup of Claude Code transcripts with hard-link dedup. Cron at 3 AM. |
| `daily-git-snapshot.sh [REPO]` | Auto-commit any uncommitted changes in REPO (default $PWD). Cron at 4 AM, or every N minutes for tighter recovery. |
| `curate_memory.py` | Find duplicates, orphans, broken links in `~/.claude/memory/`. Exit 0 if clean, 1 with findings. |
| `recap_extract.py` | Dump user/assistant messages since the last compaction boundary. Used by `/recap`. |

## Adding your own

Drop a script in here, add a row to this table. If the agent should call it directly, mention it in `CLAUDE.md` or wire it through a hook.
