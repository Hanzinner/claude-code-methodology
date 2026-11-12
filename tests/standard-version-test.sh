#!/usr/bin/env bash
# standard_version.py: agent v0 -> a hint with the changelog; updated to v1 -> silence; version raised -> only the new entry.
# SV=<path> tests another copy.
set -u
HERE=$(dirname "$(readlink -f "$0")")
SV=${SV:-$HERE/../scripts/standard_version.py}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT; mkdir -p "$T/h"
export HOME="$T/h" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_CODING_STANDARD="$T/STD.md"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; fi; }

std() {   # a standard of version $1 with changelog entries v1..v$1
    { echo "# CODING-STANDARD"; echo; echo "> **Version: $1 · 2026-09-27** (changelog at the end of the file)."
      echo; echo "A mention in the text: the section \"## Standard changelog\" below is not a section."; echo
      echo "## Standard changelog"; echo "> Every change of the rules -> version +1."
      for v in $(seq 1 "$1"); do echo "- **v$v · 2026-10-0$v** - change number $v."; echo "  continuation of entry $v"; echo; echo "  paragraph after a blank line $v"; done
    } > "$T/STD.md"
}
agent() { mkdir -p "$T/ag"; printf '# ag\n\n## Swarm protocols\n- **Standard: v%s read 2026-09-27**\n' "$1" > "$T/ag/briefing.md"; }
H() { python3 "$SV" hint "$T/ag" "$T/state"; }
L() { python3 "$SV" lag "$T/ag"; }

std 1; agent 0; rm -f "$T/state"
o=$(H); ok "v0 -> a hint"                      '[[ "$o" == *"standard is v1, you confirmed v0"* ]]'
ok "v0 -> entry v1 with its continuation"       '[[ "$o" == *"change number 1"* && "$o" == *"continuation of entry 1"* ]]'
ok "a mention in the text does not shift the changelog" '[[ "$o" != *"Every change"* ]]'
ok "a paragraph after a blank line is kept"      '[[ "$o" == *"paragraph after a blank line 1"* ]]'
o=$(H); ok "the same pair a second time today -> silence" '[[ -z "$o" ]]'
echo "1:0:2000-01-01" > "$T/state"; o=$(H); ok "the same pair but from yesterday -> reminds again" '[[ "$o" == *"you confirmed v0"* ]]'
agent 1; o=$(H); ok "updated to v1 -> silence"   '[[ -z "$o" ]]'
std 2; o=$(H); ok "raised to v2 -> only the new entry" '[[ "$o" == *"change number 2"* && "$o" != *"change number 1"* ]]'
agent 0; rm -f "$T/state"; o=$(H); ok "v0 at v2 -> both entries" '[[ "$o" == *"change number 1"* && "$o" == *"change number 2"* ]]'
printf '# ag\n' > "$T/ag/briefing.md"; rm -f "$T/state"; o=$(H)
ok "no line -> v0 and \"add it\""                '[[ "$o" == *"you confirmed v0"* && "$o" == *"has none - add it"* ]]'
agent 2; L >/dev/null; ok "lag: equal -> rc 0"   '[ $? = 0 ]'
agent 1; o=$(L); rc=$?; ok "lag: behind -> rc 1 and \"first read\"" '[ $rc = 1 ] && [[ "$o" == *"first read the changes"* ]]'
CCM_CODING_STANDARD="$T/nope.md" python3 "$SV" hint "$T/ag" >/dev/null 2>&1; ok "standard unreadable -> silence rc 0" '[ $? = 0 ]'
v=$(python3 "$SV" current); ok "current prints the number" '[ "$v" = 2 ]'
# Ukrainian forms only with CCM_LANG_EXTRA=uk
{ echo "> **Версія: 3**"; echo "## Журнал змін стандарту"; echo "- **v3** - зміна"; } > "$T/STD.md"
printf '## p\n- **Стандарт: v1 прочитано 2026-01-01**\n' > "$T/ag/briefing.md"
o=$(python3 "$SV" lag "$T/ag"); ok "Ukrainian forms ignored by default (no version found -> silence)" '[ -z "$o" ]'
o=$(CCM_LANG_EXTRA=uk python3 "$SV" hint "$T/ag"); ok "Ukrainian forms with CCM_LANG_EXTRA=uk" '[[ "$o" == *"v3, you confirmed v1"* && "$o" == *"v3** - зміна"* ]]'
echo "standard-version: $pass pass, $fail fail"; [ $fail = 0 ]
