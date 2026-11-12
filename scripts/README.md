# scripts

Utilities called from hooks or directly. All idempotent. Paths are set per script through env vars named in each header (`CLAUDE_MEMORY_DIR`, `CLAUDE_PROJECT_TRANSCRIPT_DIR`, `BACKUP_DIR`, …); defaults live under `~/.claude`.

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
| `claude_machine.py` | Run `claude -p` from a script without saving a session, with cost accounting. |
| `episodic_append.sh` | The one way to add to the "when did we do X" log: under a lock, so two agents don't swallow each other's entries. |
| `extract_scenes.sh` | Scene-change frames from a video (URL via yt-dlp, or a file); used by `/edit`. |
| `rename_session.py` | Set a custom title on a Claude Code session. |
| `transcript_tail.py` | The transcript lines of the last turn, without reading the whole file (Stop checks share it). |
| `ai-studio-to-md` | Convert Google AI Studio JSON exports to Markdown. |

## cross-review.sh

Independent review by a **different** model: a fresh `claude -p` with `--tools "Read,Grep,Glob"` reviews a diff or files against an optional requirements table and a "why" log. Self-review by the same model found 5 defects where other models found ~20 more. Usage: `cross-review.sh --model sonnet --git HEAD~1..HEAD`.

## bin/ (linked into `~/.local/bin`)

| Tool | What it does |
|---|---|
| `creds` | Read credentials from the one store (`CCM_SECRETS_DIR`) instead of copying them next to the work. |
| `rename-ref` | Rename a `.md` file and rewrite every reference to it. |
| `secret-scan` | Find secrets in the added lines of a diff, or in whole files. |
| `swap-live` | Replace a live script or hook atomically with a checked copy, keeping its permissions. |
