# scripts

Utilities called from hooks or directly. All idempotent. Resolve install path via `$CLAUDE_METHODOLOGY_DIR`, fallback `~/.claude`.

## Document extraction

| Script | Action |
|--------|--------|
| `pdf-extract.sh <pdf> [--images] [--dpi=N]` | PDF → `.txt` (full) + `.meta.txt` + `.pages/p####.txt` + optional `.images/p####.png`. |
| `html-extract.sh <html>` | HTML → `.txt` via `lynx -dump` (plain text). |
| `html-to-md.sh <html>` | HTML → `.md` via `pandoc` (GFM, preserves structure). |

System deps: `poppler-utils`, `lynx`, `pandoc`.

## Memory & persistence

| Script | Action |
|--------|--------|
| `backup-chats.sh` | Daily rsync backup of Claude Code transcripts with hard-link dedup. Cron at 3 AM. |
| `daily-git-snapshot.sh [REPO]` | Auto-commit uncommitted changes in REPO. Cron at 4 AM, or every N minutes. |
| `curate_memory.py` | Memory health (orphans, broken links, unresolved wikilinks). Exit 0 if clean, 1 with findings. |
| `recap_extract.py` | Dump user/assistant messages since the last compaction boundary. Used by `/recap`. |
