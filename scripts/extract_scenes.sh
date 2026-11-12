#!/bin/bash
# extract_scenes.sh - extracts scene-change frames from a video
# Usage: extract_scenes.sh <url_or_path> [scene_threshold] [output_dir]
#   url_or_path     - a video URL (needs yt-dlp) or a path to a local file
#   scene_threshold - 0.0..1.0, the lower the more frames (default 0.25)
#   output_dir      - where to put the result (default /tmp/edit_TIMESTAMP)
# Needs ffmpeg (always) and yt-dlp (URLs only).

set -e

INPUT="${1:?Usage: $0 <url_or_path> [threshold] [outdir]}"
THRESHOLD="${2:-0.25}"
OUTDIR="${3:-/tmp/edit_$(date +%s)}"

command -v ffmpeg >/dev/null 2>&1 || { echo "ERROR: ffmpeg is not installed" >&2; exit 127; }

mkdir -p "$OUTDIR/frames"

if [[ "$INPUT" == http* ]]; then
    command -v yt-dlp >/dev/null 2>&1 || { echo "ERROR: yt-dlp is not installed (needed for URLs)" >&2; exit 127; }
    echo "Downloading: $INPUT"
    yt-dlp -f "bv*[height<=720]+ba/b[height<=720]" \
           -o "$OUTDIR/video.%(ext)s" \
           "$INPUT" 2>&1 | tail -3
    VIDEO=$(ls "$OUTDIR"/video.* 2>/dev/null | head -1)
else
    VIDEO="$INPUT"
fi

if [ ! -f "$VIDEO" ]; then
    echo "ERROR: video file not found"
    exit 1
fi

DURATION=$(ffmpeg -i "$VIDEO" 2>&1 | grep Duration | awk '{print $2}' | tr -d ',')
echo "Video: $VIDEO"
echo "Duration: $DURATION"
echo "Extracting scenes (threshold=$THRESHOLD)..."

ffmpeg -i "$VIDEO" \
    -vf "select='gt(scene,$THRESHOLD)',showinfo" \
    -vsync vfr -q:v 3 \
    "$OUTDIR/frames/scene_%04d.jpg" 2>&1 \
  | grep -oP "pts_time:\K[0-9.]+" > "$OUTDIR/timestamps.txt"

paste <(ls "$OUTDIR/frames/" | sort) "$OUTDIR/timestamps.txt" \
  > "$OUTDIR/scenes.tsv"

FRAME_COUNT=$(ls "$OUTDIR/frames/" | wc -l)
SIZE=$(du -sh "$OUTDIR/frames/" | awk '{print $1}')

echo ""
echo "=== Result ==="
echo "Frames extracted: $FRAME_COUNT"
echo "Frames size: $SIZE"
echo "Output dir: $OUTDIR"
echo "Scenes index: $OUTDIR/scenes.tsv"
