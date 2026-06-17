#!/usr/bin/env bash
# PreToolUse hook: intercepts Read on .pdf/.html files, ensures they're
# extracted via pdf-extract.sh / html-extract.sh, and redirects the agent
# to read the .txt version instead of the raw PDF/HTML.
#
# Why: Read tool on PDF is expensive and capped (~10-20 pages/call); on
# HTML it returns tags + nav noise. Memory triggers aren't reactive — agents
# ignore them. This hook is architectural enforcement, independent of agent
# discipline.
#
# Behavior:
#   • PDF ≤ 10 MB → auto-extract silently, block Read with "use .txt"
#   • PDF > 10 MB → block with "file is large, run pdf-extract.sh manually"
#   • HTML        → auto-extract (fast), block with "use .txt"
#   • other files → pass-through (exit 0)
#
# Idempotent: pdf-extract.sh / html-extract.sh skip if .txt is newer than source.

set -euo pipefail

CLAUDE_DIR="${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}"
LARGE_PDF_MB=10

input=$(cat)
tool=$(printf '%s' "$input" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tool_name',''))")
[[ "$tool" == "Read" ]] || exit 0

file_path=$(printf '%s' "$input" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))")
[[ -n "$file_path" ]] || exit 0
[[ -f "$file_path" ]] || exit 0  # missing file — let Read tool report it

fname=$(basename "$file_path")
ext_raw="${fname##*.}"
ext=$(printf '%s' "$ext_raw" | tr '[:upper:]' '[:lower:]')

case "$ext" in
  pdf)
    base="${file_path%.*}"
    txt_path="${base}.txt"
    pages_dir="${base}.pages"

    if [[ -f "$txt_path" && "$txt_path" -nt "$file_path" ]]; then
      cat >&2 <<EOF
PDF is already extracted. Do NOT read the raw PDF — use:
  • full text:    Read('$txt_path')
  • metadata:     Read('${base}.meta.txt')
  • page N:       Read('$pages_dir/p<NNNN>.txt')   e.g. p0042.txt
  • page images:  Read('${base}.images/p<NNNN>.png') if --images was used
  • search:       bash grep -l 'pattern' $pages_dir/*.txt
EOF
      exit 2
    fi

    size_mb=$(du -m "$file_path" | cut -f1)
    if [[ $size_mb -gt $LARGE_PDF_MB ]]; then
      cat >&2 <<EOF
PDF is large ($size_mb MB > ${LARGE_PDF_MB} MB) — auto-extract skipped to avoid blocking.
Run manually:
  $CLAUDE_DIR/scripts/pdf-extract.sh "$file_path"
  (add --images if the PDF has diagrams/charts/scans)
Then Read('${base}.txt') or Read('${base}.pages/p<NNNN>.txt').
EOF
      exit 2
    fi

    if "$CLAUDE_DIR/scripts/pdf-extract.sh" "$file_path" >&2; then
      cat >&2 <<EOF

PDF auto-extracted. Read:
  • full text:  Read('$txt_path')
  • page N:     Read('$pages_dir/p<NNNN>.txt')
  • search:     bash grep -l 'pattern' $pages_dir/*.txt
If page images are needed (diagrams/charts), re-run:
  bash $CLAUDE_DIR/scripts/pdf-extract.sh "$file_path" --images
EOF
      exit 2
    else
      echo "auto-extract failed; falling back to direct Read" >&2
      exit 0
    fi
    ;;

  html|htm)
    base="${file_path%.*}"
    txt_path="${base}.txt"

    if [[ -f "$txt_path" && "$txt_path" -nt "$file_path" ]]; then
      echo "HTML is already extracted. Read('$txt_path') instead of the raw file." >&2
      exit 2
    fi

    if "$CLAUDE_DIR/scripts/html-extract.sh" "$file_path" >&2; then
      echo "HTML auto-extracted → Read('$txt_path')" >&2
      exit 2
    else
      echo "auto-extract failed; falling back to direct Read" >&2
      exit 0
    fi
    ;;
esac

exit 0
