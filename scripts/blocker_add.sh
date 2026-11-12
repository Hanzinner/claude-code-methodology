#!/usr/bin/env bash
# blocker_add.sh <project> "<what exactly is needed>" "<who clears it>" "<check command | manual>" - new blocker in
# <project folder>/BLOCKERS.md. Whoever hits the wall registers it (not the coordinator from memory). Prints the number:
# put it in the story line as "blockers: B<n>".
exec "$(dirname "$(readlink -f "$0")")/blockers.py" add "$@"
