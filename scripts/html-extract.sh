#!/usr/bin/env bash
# HTML → plain text, suitable for agent reading.
# Uses lynx -dump (browser-style rendering, strips HTML/CSS/JS/nav).
#
# Output (alongside input.html):
#   - <name>.txt — clean text as a browser would render it
#
# Usage:
#   html-extract.sh <input.html>            # output alongside source
#   html-extract.sh <input.html> <out_dir>  # output to a specific dir
#
# Idempotent: skip if .txt is newer than .html

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: html-extract.sh <input.html> [<output_dir>]" >&2
  exit 2
fi

HTML="$1"
[[ -f "$HTML" ]] || { echo "ERROR: file not found: $HTML" >&2; exit 1; }

OUT_DIR="${2:-$(dirname "$HTML")}"
mkdir -p "$OUT_DIR"
NAME=$(basename "$HTML" .html)
TXT="$OUT_DIR/$NAME.txt"

if [[ -f "$TXT" && "$TXT" -nt "$HTML" ]]; then
  echo "Already extracted: $TXT"
  exit 0
fi

# lynx -dump: browser-rendered text. -nolist drops trailing link list.
lynx -dump -nolist -width=120 -display_charset=utf-8 "$HTML" > "$TXT"

WORDS=$(wc -w < "$TXT")
SIZE_KB=$(du -k "$TXT" | cut -f1)
echo "Extracted: $TXT (${WORDS} words, ${SIZE_KB}KB)"
