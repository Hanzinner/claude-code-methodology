#!/usr/bin/env bash
# Daily backup of Claude Code chat transcripts.
# Hard-link deduplication via rsync --link-dest so disk usage stays small —
# unchanged files share inodes across day-folders.
#
# Recommended cron: 0 3 * * *  (3 AM daily)
# Retention: configurable, default 365 days.
#
# Override defaults via env:
#   BACKUP_DIR=/some/path         (default: $HOME/.claude-backups)
#   RETENTION_DAYS=90             (default: 365)
#   CLAUDE_PROJECTS_DIRS="..."    (space-separated; default: standard locations)

set -e

DATE=$(date +%Y-%m-%d)
BACKUP_DIR="${BACKUP_DIR:-$HOME/.claude-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-365}"
TARGET="$BACKUP_DIR/$DATE"

# Default: back up both user and root claude projects if they exist
DEFAULT_DIRS=()
[[ -d "$HOME/.claude/projects" ]] && DEFAULT_DIRS+=("$HOME/.claude/projects")
[[ -d /root/.claude/projects ]] && DEFAULT_DIRS+=("/root/.claude/projects")
DIRS=(${CLAUDE_PROJECTS_DIRS:-${DEFAULT_DIRS[@]}})

mkdir -p "$BACKUP_DIR" "$TARGET"

LATEST_PREV=$(ls -1d "$BACKUP_DIR"/2*-*-* 2>/dev/null | sort -r | grep -v "/$DATE$" | head -1)

for src in "${DIRS[@]}"; do
  label=$(echo "$src" | tr '/' '_' | sed 's/^_//')
  link_opt=""
  if [[ -n "$LATEST_PREV" && -d "$LATEST_PREV/$label" ]]; then
    link_opt="--link-dest=$LATEST_PREV/$label"
  fi
  rsync -a $link_opt "$src/" "$TARGET/$label/" 2>/dev/null || true
done

find "$BACKUP_DIR" -maxdepth 1 -mindepth 1 -type d -mtime +$RETENTION_DAYS -exec rm -rf {} \; 2>/dev/null || true

TOTAL=$(du -sh "$BACKUP_DIR" 2>/dev/null | awk '{print $1}')
TODAY=$(du -sh "$TARGET" 2>/dev/null | awk '{print $1}')
DAYS=$(ls -1 "$BACKUP_DIR" 2>/dev/null | grep -c '^2' || echo 0)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] backup: today=$TODAY total=$TOTAL days_kept=$DAYS"
