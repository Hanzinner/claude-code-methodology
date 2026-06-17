#!/usr/bin/env bash
# HTML → Markdown via pandoc.
# Preserves structure (headings, lists, links, tables) unlike html-extract.sh
# which produces plain text.
#
# Output (alongside input.html):
#   - <name>.md — GitHub Flavored Markdown, no line wrapping
#
# Usage:
#   html-to-md.sh <input.html>            # output alongside source
#   html-to-md.sh <input.html> <out_dir>  # output to a specific dir
#
# Idempotent: skip if .md is newer than .html

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: html-to-md.sh <input.html> [<output_dir>]" >&2
  exit 2
fi

HTML="$1"
[[ -f "$HTML" ]] || { echo "ERROR: file not found: $HTML" >&2; exit 1; }

OUT_DIR="${2:-$(dirname "$HTML")}"
mkdir -p "$OUT_DIR"
NAME=$(basename "$HTML" .html)
NAME="${NAME%.htm}"
MD="$OUT_DIR/$NAME.md"

if [[ -f "$MD" && "$MD" -nt "$HTML" ]]; then
  echo "Already converted: $MD"
  exit 0
fi

# pandoc options:
#   --wrap=none → no line breaks (better for grep/diffs)
#   --markdown-headings=atx → # H1 instead of === underline
#   --strip-comments → drop HTML comments
#   -t gfm → GitHub Flavored Markdown (tables, strikethrough, autolinks)
pandoc "$HTML" \
  -f html -t gfm \
  --wrap=none \
  --markdown-headings=atx \
  --strip-comments \
  -o "$MD"

WORDS=$(wc -w < "$MD")
SIZE_KB=$(du -k "$MD" | cut -f1)
echo "Converted: $MD (${WORDS} words, ${SIZE_KB}KB)"
