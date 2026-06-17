#!/usr/bin/env bash
# PDF → text + optional images, for agent reading of long PDFs.
#
# Output (alongside input.pdf):
#   - <name>.txt            — full text (layout preserved)
#   - <name>.meta.txt       — metadata (pages, title, author, size)
#   - <name>.pages/         — per-page text, p0001.txt, p0002.txt, ...
#   - <name>.images/        — (opt-in via --images) per-page PNGs, p0001.png, ...
#                              useful for PDFs with diagrams/charts/scanned content
#
# Usage:
#   pdf-extract.sh <input.pdf> [out_dir] [--images] [--dpi=N]
#
# Examples:
#   pdf-extract.sh book.pdf                        # text only
#   pdf-extract.sh book.pdf --images               # text + PNG @ 150 dpi
#   pdf-extract.sh book.pdf --images --dpi=200     # text + PNG @ 200 dpi
#   pdf-extract.sh book.pdf /tmp/out --images      # custom output dir
#
# Idempotent: skip when results already exist and are newer than the PDF.

set -euo pipefail

# --- arg parsing -----------------------------------------------------------
PDF=""
OUT_DIR=""
WANT_IMAGES=0
DPI=150

while [[ $# -gt 0 ]]; do
  case "$1" in
    --images)      WANT_IMAGES=1 ;;
    --dpi=*)       DPI="${1#--dpi=}" ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    --*)
      echo "ERROR: unknown flag: $1" >&2
      exit 2
      ;;
    *)
      if [[ -z "$PDF" ]]; then
        PDF="$1"
      elif [[ -z "$OUT_DIR" ]]; then
        OUT_DIR="$1"
      else
        echo "ERROR: too many positional args (PDF and out_dir already set): $1" >&2
        exit 2
      fi
      ;;
  esac
  shift
done

if [[ -z "$PDF" ]]; then
  echo "usage: pdf-extract.sh <input.pdf> [out_dir] [--images] [--dpi=N]" >&2
  exit 2
fi
[[ -f "$PDF" ]] || { echo "ERROR: file not found: $PDF" >&2; exit 1; }

if [[ -z "$OUT_DIR" ]]; then
  OUT_DIR=$(dirname "$PDF")
fi
mkdir -p "$OUT_DIR"

NAME=$(basename "$PDF" .pdf)
FULL_TXT="$OUT_DIR/$NAME.txt"
META_TXT="$OUT_DIR/$NAME.meta.txt"
PAGES_DIR="$OUT_DIR/$NAME.pages"
IMAGES_DIR="$OUT_DIR/$NAME.images"

# --- idempotency check -----------------------------------------------------
TEXT_OK=0
IMAGES_OK=0
[[ -f "$FULL_TXT" && "$FULL_TXT" -nt "$PDF" ]] && TEXT_OK=1
if [[ $WANT_IMAGES -eq 1 ]]; then
  [[ -d "$IMAGES_DIR" && "$IMAGES_DIR" -nt "$PDF" ]] && IMAGES_OK=1
else
  IMAGES_OK=1
fi

if [[ $TEXT_OK -eq 1 && $IMAGES_OK -eq 1 ]]; then
  echo "Already extracted (re-run: rm $FULL_TXT). Output:"
  echo "  $FULL_TXT"
  [[ -f "$META_TXT" ]] && echo "  $META_TXT"
  [[ -d "$PAGES_DIR" ]] && echo "  $PAGES_DIR/ ($(ls "$PAGES_DIR" | wc -l) text pages)"
  [[ -d "$IMAGES_DIR" ]] && echo "  $IMAGES_DIR/ ($(ls "$IMAGES_DIR" | wc -l) image pages)"
  exit 0
fi

# --- metadata --------------------------------------------------------------
echo "Extracting metadata…"
pdfinfo "$PDF" > "$META_TXT" 2>&1 || echo "(pdfinfo failed)" >> "$META_TXT"
PAGE_COUNT=$(grep -i "^Pages:" "$META_TXT" | awk '{print $2}' || echo "?")
echo "  pages: $PAGE_COUNT"

# --- text ------------------------------------------------------------------
if [[ $TEXT_OK -eq 0 ]]; then
  echo "Extracting full text (layout preserved)…"
  pdftotext -layout "$PDF" "$FULL_TXT"
  WORDS=$(wc -w < "$FULL_TXT")
  SIZE_KB=$(du -k "$FULL_TXT" | cut -f1)
  echo "  full text: $FULL_TXT (${WORDS} words, ${SIZE_KB}KB)"

  echo "Extracting per-page texts…"
  mkdir -p "$PAGES_DIR"
  rm -f "$PAGES_DIR"/p*.txt
  if [[ "$PAGE_COUNT" =~ ^[0-9]+$ ]]; then
    for ((p=1; p<=PAGE_COUNT; p++)); do
      page_file=$(printf "$PAGES_DIR/p%04d.txt" "$p")
      pdftotext -layout -f "$p" -l "$p" "$PDF" "$page_file"
    done
    echo "  pages: $PAGES_DIR/ ($PAGE_COUNT text files)"
  else
    echo "  (page count unknown — skipping per-page text split)"
  fi
fi

# --- images (opt-in) -------------------------------------------------------
if [[ $WANT_IMAGES -eq 1 && $IMAGES_OK -eq 0 ]]; then
  echo "Rendering pages → PNG at ${DPI} dpi…"
  mkdir -p "$IMAGES_DIR"
  rm -f "$IMAGES_DIR"/p*.png
  # pdftoppm output naming: prefix-1.png, prefix-2.png, ...
  # Rename to p0001.png so the index matches .pages/.
  TMP_PREFIX="$IMAGES_DIR/_tmp"
  pdftoppm -png -r "$DPI" "$PDF" "$TMP_PREFIX"
  for f in "$IMAGES_DIR"/_tmp-*.png; do
    [[ -f "$f" ]] || continue
    num=$(basename "$f" .png | sed 's/_tmp-//')
    target=$(printf "$IMAGES_DIR/p%04d.png" "$num")
    mv "$f" "$target"
  done
  N_IMAGES=$(ls "$IMAGES_DIR"/p*.png 2>/dev/null | wc -l)
  IMG_SIZE_MB=$(du -sm "$IMAGES_DIR" | cut -f1)
  echo "  images: $IMAGES_DIR/ ($N_IMAGES PNG files, ${IMG_SIZE_MB}MB total)"
fi

# --- guidance --------------------------------------------------------------
echo ""
echo "Done. Read via:"
echo "  • full text:   Read('$FULL_TXT')"
echo "  • metadata:    Read('$META_TXT')"
echo "  • page N:      Read('$PAGES_DIR/p<NNNN>.txt')   e.g. p0042.txt"
[[ $WANT_IMAGES -eq 1 ]] && \
  echo "  • page image N: Read('$IMAGES_DIR/p<NNNN>.png')   e.g. p0042.png (for diagrams/charts)"
echo "  • search:      grep -l 'pattern' $PAGES_DIR/*.txt | head"
