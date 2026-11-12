#!/usr/bin/env bash
# extract_scenes.sh: needs ffmpeg; skips cleanly without it. ES=<path> tests another copy.
HERE=$(dirname "$(readlink -f "$0")")
ES=${ES:-$HERE/../scripts/extract_scenes.sh}
if ! command -v ffmpeg >/dev/null 2>&1; then echo "extract-scenes: SKIP (ffmpeg is not installed - nothing was tested)"; exit 0; fi
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HOME="$T/h" CLAUDE_METHODOLOGY_CONF=/nonexistent; mkdir -p "$HOME"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }
# synthetic video: 3 one-second black/white/black clips = 2 hard scene changes
ffmpeg -loglevel error -f lavfi -i color=c=black:s=64x64:d=1:r=10 -f lavfi -i color=c=white:s=64x64:d=1:r=10 -f lavfi -i color=c=black:s=64x64:d=1:r=10 \
  -filter_complex "[0][1][2]concat=n=3:v=1:a=0" -pix_fmt yuv420p "$T/v.mp4" 2>/dev/null
ok "0 fixture video created" '[ -s "$T/v.mp4" ]'
out=$(bash "$ES" "$T/v.mp4" 0.3 "$T/out" 2>&1); rc=$?
ok "1 local file: rc 0" '[ $rc = 0 ]'
ok "2 frames written for the scene changes" '[ "$(ls "$T/out/frames" | wc -l)" -ge 2 ]'
ok "3 scenes.tsv lists frame + timestamp" '[ "$(wc -l < "$T/out/scenes.tsv")" -ge 2 ] && grep -q "scene_0001.jpg" "$T/out/scenes.tsv"'
ok "4 result block printed" 'grep -q "Frames extracted:" <<<"$out"'
bash "$ES" "$T/missing.mp4" 0.3 "$T/out2" >/dev/null 2>&1; ok "5 missing file -> rc 1" '[ $? = 1 ]'
bash "$ES" >/dev/null 2>&1; ok "6 no arguments -> usage error" '[ $? != 0 ]'
echo "extract-scenes: $pass pass, $fail fail"; [ $fail = 0 ]
