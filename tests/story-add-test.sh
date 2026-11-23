#!/usr/bin/env bash
# story_add.sh / story_add.py in a sandbox (temp workspace, HOME, transcripts; no config file; real ROADMAPs untouched).
# Number within an epic with gaps (max+1), project-wide numbering, the S<n> format, the "New" section, --from-human
# with and without a matching message, 5 parallel runs -> 5 different numbers, --epic E99 -> refused, no ROADMAP -> rc 4,
# owner and mode of ROADMAP kept, older "## ЕПІК" headings, CCM_PROJECTS_GLOB. SA=<path to story_add.sh> tests another copy.
set -uo pipefail
NAME=story-add-test
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SA=${SA:-$HERE/../scripts/story_add.sh}
own() { python3 -c 'import os,sys; s=os.stat(sys.argv[1]); print("%d:%d %o" % (s.st_uid, s.st_gid, s.st_mode & 0o7777))' "$1"; }   # stat -c "%u:%g %a"; BSD stat has no -c
T=$(mktemp -d) && [[ -d "$T" && "$T" != / ]] || { echo "no temp dir" >&2; exit 2; }
trap 'rm -rf -- "$T"' EXIT   # the test's own sandbox
export CCM_TEST=1 HOME="$T/home" CLAUDE_METHODOLOGY_CONF=/nonexistent
export STORY_ADD_REPO="$T/ws" CLAUDE_PROJECTS_DIR="$T/projects" CCM_TIMEZONE=Asia/Dubai CCM_HUMAN_NAME=Alex
export CLAUDE_CODE_SESSION_ID=11111111-2222-3333-4444-555555555555
unset CCM_PROJECTS_GLOB CCM_WORKSPACE
mkdir -p "$HOME"
P=0; F=0
ok()   { P=$((P+1)); echo "ok   $1"; }
bad()  { F=$((F+1)); echo "FAIL $1"; }
check() { if eval "$2"; then ok "$1"; else bad "$1 [$2] out=${OUT:-}"; fi; }
run()  { OUT=$("$SA" "$@" 2>&1); RC=$?; LAST=${OUT##*$'\n'}; }
rmf()  { echo "$STORY_ADD_REPO/Project-$1/ROADMAP.md"; }
mk()   { mkdir -p "$STORY_ADD_REPO/Project-$1"; cat > "$(rmf "$1")"; }
ROOT=0; [[ $(id -u) == 0 ]] && ROOT=1
WIN=0; case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) WIN=1 ;; esac   # Git Bash + native Python on Windows
skip() { echo "SKIP on Windows: $1"; }

mkdir -p "$CLAUDE_PROJECTS_DIR/-home-x"
printf '%s\n' \
  '{"type":"user","origin":{"kind":"human"},"entrypoint":"cli","timestamp":"2026-11-22T10:39:00.000Z","message":{"role":"user","content":"the \"back\" button in the tree does nothing, file it"}}' \
  '{"type":"assistant","timestamp":"2026-11-22T10:40:00.000Z","message":{"role":"assistant","content":[{"type":"text","text":"assistant: a phrase only the assistant said"}]}}' \
  > "$CLAUDE_PROJECTS_DIR/-home-x/$CLAUDE_CODE_SESSION_ID.jsonl"

# --- 1. epics numbered within the epic, gaps -> max+1; a mention of a cancelled one takes a number too
mk Game <<'EOF'
# Game - roadmap

## EPIC 1 - Workbench
- ✅ **[E1.S1] Build**
- ⏳ **[E1.S2] Fork**

## EPIC 7 - Bugs in the game
- ✅ **[E7.S1] List**
- ⏳ **[E7.S2] Wheel**
- [D] the human: "yes" -> E7.S8(a) and E7.S8(b) - one branch
- ✅ **[E7.S5] Tree**
- ✖ **[E7.S9] Zoom** - cancelled
- 🔮 [E7.S2+] Every bug is its own story

## EPIC 8 - New things the original lacks
- ⏳ **[E8.S1] Button**
EOF
chmod 640 "$(rmf Game)"; (( ROOT )) && chown 65534:65534 "$(rmf Game)"
OWN=$(own "$(rmf Game)")
run Game "Map: holes in the forest" --epic E7
check "epic with gaps: E7 -> E7.S10 (max 9 + 1)" '[[ $RC == 0 && $LAST == E7.S10 ]]'
check "the line is at the end of EPIC 7, before EPIC 8" \
  '[[ $(grep -n "E7.S10" "$(rmf Game)" | cut -d: -f1) == $(( $(grep -n "^## EPIC 8" "$(rmf Game)" | cut -d: -f1) - 2 )) ]]'
check "line format \"- ⏳ **[E7.S10] summary**\"" 'grep -qxF -- "- ⏳ **[E7.S10] Map: holes in the forest**" "$(rmf Game)"'
if (( WIN )); then skip "owner and mode kept - chmod 640 is not kept on NTFS (Git Bash shows 644), files have no Unix owner"
else check "owner and mode kept ($OWN)" '[[ $(own "$(rmf Game)") == "$OWN" && $OWN == *" 640" ]]'; fi
run Game "New button" --epic 1
check "another epic: --epic 1 -> E1.S3" '[[ $RC == 0 && $LAST == E1.S3 ]]'

# --- 2. "New": without --epic in a project with epics -> [S<max+1>], the section is created once
run Game "Something without an epic"
check "without --epic -> S11 (max S in the project 10 + 1)" '[[ $RC == 0 && $LAST == S11 ]]'
run Game "Another thing without an epic"
check "second one without --epic -> S12" '[[ $RC == 0 && $LAST == S12 ]]'
check "exactly one \"## New\", at the end, both lines under it" \
  '[[ $(grep -c "^## New$" "$(rmf Game)") == 1 && $(tail -n 2 "$(rmf Game)" | grep -c "^- ⏳ \*\*\[S1[12]\]") == 2 ]]'

# --- 3. --from-human: a message found -> "from <human>" tail; not found / assistant only -> rc 2, file unchanged
run Game "Tree: back" --epic E7 --from-human 'the "BACK" button in the tree   does nothing'
if python3 -c 'import sys, zoneinfo; zoneinfo.ZoneInfo(sys.argv[1])' Asia/Dubai 2>/dev/null; then
check "--from-human with a message -> E7.S11 with the message time (CCM_TIMEZONE, UTC+4) and the fragment" \
  '[[ $RC == 0 && $LAST == E7.S11 ]] && grep -qF -- "- ⏳ **[E7.S11] Tree: back** · from Alex 2026-11-22 14:39 \"the \"BACK\" button in the tree does nothing\"" "$(rmf Game)"'
else   # Windows Python without the tzdata package: the system's zone is used (lib/ccm_time.py), so the hour is not fixed
check "--from-human with a message -> E7.S11 with a message time and the fragment (no zone database: system zone)" \
  '[[ $RC == 0 && $LAST == E7.S11 ]] && grep -qE -- "^- ⏳ \*\*\[E7.S11\] Tree: back\*\* · from Alex 2026-11-2[123] [0-9]{2}:[0-9]{2} \"the \"BACK\" button in the tree does nothing\"" "$(rmf Game)"'
fi
H=$(cksum < "$(rmf Game)")
run Game "Made up" --epic E7 --from-human "nobody ever typed this here"
check "--from-human with no such message -> rc 2, nothing added" '[[ $RC == 2 && $(cksum < "$(rmf Game)") == "$H" ]]'
run Game "Made up" --epic E7 --from-human "a phrase only the assistant said"
check "--from-human with the assistant's text -> rc 2, nothing added" '[[ $RC == 2 && $(cksum < "$(rmf Game)") == "$H" ]]'
run Game "Made up" --epic E7 --from-human "ok yes"
check "--from-human with a fragment under 8 chars -> rc 1, nothing added" '[[ $RC == 1 && $(cksum < "$(rmf Game)") == "$H" ]]'

# --- 4. --epic E99 -> a clear refusal
run Game "Where?" --epic E99
check "--epic E99 -> rc 3 \"no section ... EPIC 99\", file unchanged" \
  '[[ $RC == 3 && $OUT == *"no section \"## EPIC 99"* && $(cksum < "$(rmf Game)") == "$H" ]]'

# --- 5. project-wide numbering (E5.S99, E4.S100)
mk Shop <<'EOF'
# Shop
## EPIC 4 - Sales
- ✅ **[E4.S1] Accounts**
- ⏳ **[E4.S100] Consent**
## EPIC 5 - Release
- ⏳ **[E5.S98] Sandbox**
- ⏳ **[E5.S99] Won**
EOF
run Shop "New in the fifth" --epic E5
check "project-wide numbering: --epic E5 -> E5.S101 (not E5.S100)" '[[ $RC == 0 && $LAST == E5.S101 ]]'
check "line E5.S101 is the last of the file (end of EPIC 5)" '[[ $(tail -n 1 "$(rmf Shop)") == *"[E5.S101]"* ]]'

# --- 6. the S<n> format
mk Clip <<'EOF'
# Clip - roadmap

## EPIC 1 - clipboard

- ✅ **S1 · access between laptops**
- 🔄 **S2 · files and folders**
- 🔄 **S4 · autostart** (S·60)
EOF
run Clip "pictures" --epic 1
check "S<n> format: --epic 1 -> S5 under EPIC 1" '[[ $RC == 0 && $LAST == S5 ]] && [[ $(sed -n 8p "$(rmf Clip)") == "- ⏳ **S5 · pictures**" ]]'
run Project-Clip "sound"
check "S<n> format without --epic, project given with its prefix -> S6 in \"## New\"" '[[ $RC == 0 && $LAST == S6 ]] && [[ $(tail -n 2 "$(rmf Clip)" | head -n1) == "## New" ]]'

# --- 7. older headings "## ЕПІК <n>" / "## Нове" are recognized
mk Old <<'EOF'
# Old
## ЕПІК 2 — bugs
- ⏳ **[E2.S4] wheel**

## Нове
- ⏳ **[S5] loose**
EOF
run Old "lines" --epic E2
check "older \"## ЕПІК 2\" heading -> E2.S5 right under it" '[[ $RC == 0 && $LAST == E2.S5 && $(sed -n 4p "$(rmf Old)") == "- ⏳ **[E2.S5] lines**" ]]'
run Old "menu"
check "older \"## Нове\" -> used, no second section created" '[[ $RC == 0 && $LAST == S6 && $(grep -c "^## New" "$(rmf Old)") == 0 && $(tail -n 1 "$(rmf Old)") == "- ⏳ **[S6] menu**" ]]'

# --- 8. 5 parallel runs -> 5 different numbers, 5 lines
for i in 1 2 3 4 5; do "$SA" Game "Parallel $i" --epic E8 > "$T/par.$i" 2>&1 & done
wait
codes=$(for i in 1 2 3 4 5; do tail -n1 "$T/par.$i"; done | sort -u | tr '\n' ' ')
check "5 parallel -> 5 different codes E8.S2-S6 ($codes)" '[[ $codes == "E8.S2 E8.S3 E8.S4 E8.S5 E8.S6 " ]]'
check "5 parallel -> 5 \"Parallel\" lines in the file" '[[ $(grep -c "Parallel" "$(rmf Game)") == 5 ]]'
check "after all writes owner/mode the same, no tmp left" \
  '[[ $(own "$(rmf Game)") == "$OWN" && -z $(find "$STORY_ADD_REPO" -name "*.tmp") ]]'

# --- 9. no ROADMAP -> rc 4 with a hint; CCM_PROJECTS_GLOB picks other folders
mkdir -p "$STORY_ADD_REPO/Project-Empty"
run Empty "something"
check "no ROADMAP -> rc 4 naming new_project.sh" '[[ $RC == 4 && $OUT == *"new_project.sh"* ]]'
mkdir -p "$STORY_ADD_REPO/Work-Tool"; printf '# Tool\n## EPIC 1\n- ⏳ **[E1.S1] a**\n' > "$STORY_ADD_REPO/Work-Tool/ROADMAP.md"
OUT=$(CCM_PROJECTS_GLOB='Work-*' "$SA" Tool "b" --epic 1 2>&1); RC=$?; LAST=${OUT##*$'\n'}
check "CCM_PROJECTS_GLOB=Work-* -> Work-Tool, E1.S2" '[[ $RC == 0 && $LAST == E1.S2 ]] && grep -qF "[E1.S2] b" "$STORY_ADD_REPO/Work-Tool/ROADMAP.md"'
run Game
check "wrong usage -> rc 1 with help" '[[ $RC == 1 && $OUT == *"story_add.py"* ]]'

# --- 10. scope: the test checked as many lines as it added
check "Game: exactly 10 story lines added by the test (scope of the check)" '[[ $(grep -c "^- ⏳ \*\*\[\(E[0-9]*\.\)\?S[0-9]*\] \(Map\|New button\|Something\|Another\|Tree\|Parallel\)" "$(rmf Game)") == 10 ]]'

echo "$NAME: $P pass, $F fail"
[[ $F == 0 ]]
