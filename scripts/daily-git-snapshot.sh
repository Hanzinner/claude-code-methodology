#!/usr/bin/env bash
# Daily git snapshot of a working directory.
# Auto-commits all uncommitted changes so the working tree stays clean
# and recovery via `git log` is always possible.
#
# Recommended cron: 0 4 * * *  (4 AM daily). Or run every N minutes for
# tighter recovery windows — empty commits are skipped.
#
# Usage:
#   daily-git-snapshot.sh                        # uses $PWD
#   daily-git-snapshot.sh /path/to/repo
#   REPO=/path daily-git-snapshot.sh
#   LOG=/tmp/snapshot.log daily-git-snapshot.sh  # log file (default: stderr)

set -euo pipefail

REPO="${1:-${REPO:-$PWD}}"
LOG="${LOG:-/dev/stderr}"

cd "$REPO"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "$(date -Iseconds) ERROR: not a git repo: $REPO" >> "$LOG"
  exit 1
fi

if git diff-index --quiet HEAD -- && [ -z "$(git ls-files --others --exclude-standard)" ]; then
  echo "$(date -Iseconds) no changes — skipping" >> "$LOG"
  exit 0
fi

git add -A
date_str=$(date +%Y-%m-%d)
count=$(git diff --cached --name-only | wc -l)
git commit -m "auto: daily snapshot ${date_str} (${count} file(s))" >> "$LOG" 2>&1
echo "$(date -Iseconds) commit OK ($count files)" >> "$LOG"
