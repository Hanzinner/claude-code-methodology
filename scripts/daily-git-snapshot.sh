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

. "$(dirname "$(readlink -f "$0")")/../lib/ccm_compat.sh"   # ccm_now_iso: no date -Iseconds on a stock macOS; git_snapshot_2fail_check.sh reads these times
REPO="${1:-${REPO:-$PWD}}"
LOG="${LOG:-/dev/stderr}"

cd "$REPO"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "$(ccm_now_iso) ERROR: not a git repo: $REPO" >> "$LOG"
  exit 1
fi

if git diff-index --quiet HEAD -- && [ -z "$(git ls-files --others --exclude-standard)" ]; then
  echo "$(ccm_now_iso) no changes — skipping" >> "$LOG"
  exit 0
fi

# A failed add/commit must leave a FAIL line: under set -e it used to exit silently, the last line in the log stayed the
# previous "commit OK", and git_snapshot_2fail_check.sh saw nothing wrong.
if ! git add -A >> "$LOG" 2>&1; then
  echo "$(ccm_now_iso) FAIL: git add -A in $REPO" >> "$LOG"; exit 1
fi
date_str=$(date +%Y-%m-%d)
count=$(( $(git diff --cached --name-only | wc -l) ))
if git commit -m "auto: daily snapshot ${date_str} (${count} file(s))" >> "$LOG" 2>&1; then
  echo "$(ccm_now_iso) commit OK ($count files)" >> "$LOG"
else
  echo "$(ccm_now_iso) FAIL: git commit in $REPO (see the lines above)" >> "$LOG"; exit 1
fi
