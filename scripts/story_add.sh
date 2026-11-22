#!/usr/bin/env bash
# story_add.sh <project> "<summary>" [--epic E7] [--from-human "<fragment>"] - add a story with the next number to ROADMAP.md.
# Thin wrapper: all the logic (number format, lock, atomic write) is in story_add.py next to it; help: story_add.py without arguments.
# The last line of output is the code itself: code=$(story_add.sh Shop "..." --epic E7 | tail -n1)
exec python3 "$(dirname "$(readlink -f "$0")")/story_add.py" "$@"
