#!/usr/bin/env bash
# rename_agent.sh in a sandbox: a dry run changes nothing (tree hash); --apply does steps 1-5; whole-word replacement; history
# ([D] lines, ROADMAP outside the "Lead:" header, closed sections, decisions/MISTAKES/episodic/logs/inboxes) is not changed;
# .aliases; refusals (rc 4) and usage (rc 2); letters (the real inbox_post.sh) only to the team; a lost letter -> rc 6;
# the Ukrainian markers with CCM_LANG_EXTRA=uk. RA=<path> tests another copy.
set -u
HERE=$(dirname "$(readlink -f "$0")")
RA=${RA:-$HERE/../scripts/rename_agent.sh}
T=$(mktemp -d) || exit 2; [[ -d "$T" ]] || exit 2; trap 'rm -rf "$T"' EXIT; chmod 755 "$T"
R="$T/repo"; A="$R/Agents"; H="$T/home"
mkdir -p "$A"/{Foo-Ops,Foo-HQ,Foo-Dev,Foo-OpsX,Bar-Dev,Keeper,Solo,Other,Alias-Owner} "$A/Grp/Grp-View" "$A/_example-agent" \
         "$R"/{Project-Foo,Project-Bar} "$H/.claude/agent-identity" "$H/.claude/sessions" "$T/mode"
for d in "$A"/*/ "$A/Grp/Grp-View/"; do b=$(basename "$d"); [[ $b == Grp ]] && continue
    echo "# $b" > "$d/briefing.md"; printf '# %s - inbox\n\n## New\n\n## Processed\n' "$b" > "$d/inbox.md"; done
echo "Template mentions Foo-Ops." >> "$A/_example-agent/briefing.md"
# the renamed one: a briefing with its own path, old-style todo files with the name in them, another file with the name - untouched
cat > "$A/Foo-Ops/briefing.md" <<'E'
# Foo-Ops
Briefing: Agents/Foo-Ops/briefing.md · todo: Foo-Ops-agent-TODO.md
E
echo "- [ ] task of Foo-Ops" > "$A/Foo-Ops/Foo-Ops-agent-TODO.md"
echo "- [ ] for the human from Foo-Ops" > "$A/Foo-Ops/Foo-Ops-human-TODO.md"
echo "note" > "$A/Foo-Ops/Foo-Ops-notes.md"
# mentions: whole word yes, substring / dash continuation no
cat > "$R/Project-Foo/ROADMAP.md" <<'E'
# Foo - roadmap

> Lead: Foo-HQ, deploys - Foo-Ops. Legend: done · active
- E1.S1 owner **Foo-Ops** (since 22.10).
- E1.S2 Foo-OpsX and xFoo-Ops and Foo-Ops-Legacy - leave alone
- E1.S3 a letter in Agents/Foo-Ops/inbox.md, end of sentence Foo-Ops.
- [D] the human 2026-11-22 10:53 (in the Foo-Ops tab): yes
E
printf 'hq = "Foo-HQ"\ntest = ""\n' > "$R/Project-Foo/release.toml"
printf '| Deploy | **Foo-Ops** |\n| Other | Foo-OpsX |\n- [D] 2026-10-22 Foo-Ops took deploys\n' > "$R/Project-Foo/FILE-OWNERSHIP.md"
printf 'deploy/** Foo-Ops\nweb/** Foo-OpsX\n' > "$R/Project-Foo/OWNERS"
printf 'hq = "Foo-Ops"\n' > "$R/Project-Bar/release.toml"; printf '# Bar\n\n> Lead: Keeper. Legend\n' > "$R/Project-Bar/ROADMAP.md"
printf 'Deploy questions go to Foo-Ops.\nowner **Foo-Ops**, a letter in Agents/Foo-Ops/inbox.md; Foo-OpsX and xFoo-Ops and Foo-Ops-Legacy - leave alone\n' >> "$A/Other/briefing.md"
echo "Neighbour: Foo-Ops (group)." >> "$A/Grp/Grp-View/briefing.md"
printf '## Open\n- [ ] waiting for Foo-Ops\n## Done\n- [x] letter from Foo-Ops closed\n## Next\n- [ ] ask Foo-Ops\n' > "$A/Foo-HQ/agent-TODO.md"
# history outside the file list - always kept
mkdir -p "$R/decisions" "$R/episodic" "$A/Foo-HQ/logs"
echo "Foo-Ops decided" > "$R/decisions/0001-2026-11-22.md"; echo "## 2026-11-22 · Foo-Ops · mistake" > "$R/MISTAKES.md"
echo "Foo-Ops did" > "$R/episodic/2026-11.md"; echo "Foo-Ops start" > "$A/Foo-HQ/logs/run.log"; echo '{"a":"Foo-Ops"}' > "$A/Foo-HQ/logs/x.jsonl"
printf '# Other - inbox\n\n## New\n\n## Processed\n- [x] from Foo-Ops\n' > "$A/Other/inbox.md"
echo "- [ ] Foo-Ops has not done it yet" > "$A/Solo/agent-TODO.md"   # not the team -> keep
echo "- [ ] already a new one" > "$A/Solo/Solo2-agent-TODO.md"         # a todo name clash when Solo -> Solo2
echo "- [ ] old style" > "$A/Solo/Solo-agent-TODO.md"
cat > "$R/AGENTS.md" <<'E'
| Agent | Owns (files, domains) | Doesn't touch | Briefing |
|---|---|---|---|
| Foo-Ops | DevOps of Foo | other projects | `Agents/Foo-Ops/briefing.md` |
| **Foo-OpsX** | other | - | `Agents/Foo-OpsX/briefing.md` |
E
echo "Ops-old" > "$A/Alias-Owner/.aliases"
printf '# comment Foo-Ops\nFoo-HQ\nFoo-Ops\nFoo-OpsX\n' > "$T/wga"
echo auto > "$T/mode/Foo-Ops"; echo off > "$T/mode/Foo-OpsX"
I="$H/.claude/agent-identity"
echo "$A/Foo-Ops" > "$I/s-live"; echo "$A/Foo-Ops/" > "$I/s-slash"; echo "$A/Foo-OpsX" > "$I/s-x"
ps0=$(cut -d' ' -f22 /proc/$$/stat 2>/dev/null)   # no /proc (macOS): empty; the script checks only that the pid exists there
printf '{"pid": %s, "procStart": "%s", "sessionId": "s-live", "name": "workspace-7", "status": "idle"}\n' $$ "$ps0" > "$H/.claude/sessions/1.json"
chmod 640 "$A/Other/briefing.md"
if [[ $(id -u) == 0 ]]; then chown 65534:65534 "$A/Other/briefing.md"; fi
# uid:gid:mode and the tree snapshot in Python: BSD stat has no -c, BSD find no -printf, macOS no sha256sum
own() { python3 -c 'import os,sys; s=os.stat(sys.argv[1]); print("%d:%d:%o" % (s.st_uid, s.st_gid, s.st_mode & 0o7777))' "$1"; }
own0=$(own "$A/Other/briefing.md")
cat > "$T/snap.py" <<'PY'
# One line per path (type, owner, mode, size, link, content hash). home/Library is left out: the system python3 of a
# stock macOS can keep its bytecode cache there (sys.pycache_prefix under ~/Library/Caches), so a Python start under the
# test's HOME adds files that are not the script's doing. A failed check lists what changed.
import hashlib, os, stat, sys
paths = []
for top in sys.argv[1:]:
    paths.append(top)
    for root, dirs, files in os.walk(top):          # like find: links are listed, not followed
        dirs[:] = [d for d in dirs if os.path.join(root, d) != os.path.join("home", "Library")]
        paths += [os.path.join(root, n) for n in dirs + files]
for p in sorted(paths):
    st = os.lstat(p)
    link = os.readlink(p) if stat.S_ISLNK(st.st_mode) else ""
    sha = hashlib.sha256(open(p, "rb").read()).hexdigest() if stat.S_ISREG(st.st_mode) else ""
    print(f"{p}|{stat.S_IFMT(st.st_mode)}|{st.st_uid}:{st.st_gid}|{st.st_mode & 0o7777:o}|{st.st_size}|{link}|{sha}")
PY
export HOME="$H" CLAUDE_METHODOLOGY_CONF=/nonexistent CCM_TEST=1 CCM_WORKSPACE="$R" CCM_AGENTS_DIR="$A" \
       CCM_ALARM_MODE_DIR="$T/mode" CCM_WORK_GUARD_AGENTS="$T/wga" CCM_PROJECTS_GLOB='Project-*' CCM_LANG_EXTRA=""
run() { bash "$RA" "$@" > "$T/out" 2>&1; echo $?; }
snapls() { (cd "$T" && python3 "$T/snap.py" repo home mode wga); }
snap() { snapls | cksum; }
got() { grep -l "Agent $1 was renamed to $2" "$A"/*/inbox.md "$A"/*/*/inbox.md 2>/dev/null | sed "s|$A/||;s|/inbox.md||" | sort | tr '\n' ' '; }
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; sed 's/^/   /' "$T/out"; fi; }

hist() { python3 -c 'import hashlib,sys; [print(hashlib.sha256(open(f,"rb").read()).hexdigest(), f) for f in sys.argv[1:]]' "$R/decisions/0001-2026-11-22.md" "$R/MISTAKES.md" "$R/episodic/2026-11.md" "$A/Foo-HQ/logs/run.log" "$A/Foo-HQ/logs/x.jsonl" "$A/Other/inbox.md" "$A/_example-agent/briefing.md"; }
hs0=$(hist); h0=$(snap); snapls > "$T/snap0"; rc=$(run Foo-Ops Foo-DevOps)
ok "1 dry run: rc 0, the tree (incl. identities, mode, the work-guard list, inboxes) byte for byte the same" '[ "$rc" = 0 ] && { [ "$(snap)" = "$h0" ] || { echo "   changed by the dry run:"; snapls | diff "$T/snap0" - | head -20; false; }; }'
ok "1b the plan has steps 1-5" '( for s in "== 1." "== 2." "== 3." "== 4." "== 5."; do grep -qF "$s" "$T/out" || exit 1; done )'
ok "1c plan: live mentions (Lead header, FILE-OWNERSHIP, OWNERS, briefing) before 4b, history ([D], ROADMAP outside the header, Done) in 4b, no substrings" '( L=$(sed -n "/^== 4\. /,/^== 4b/p" "$T/out"); Hs=$(sed -n "/^== 4b/,/^== 5/p" "$T/out"); echo "$L" | grep -q "Project-Foo/ROADMAP.md:3:" && echo "$L" | grep -q "Project-Foo/FILE-OWNERSHIP.md:1:" && echo "$L" | grep -q "Project-Foo/OWNERS:1:" && ! echo "$L" | grep -q "OWNERS:2:" && echo "$L" | grep -q "Agents/Other/briefing.md:2:" && ! echo "$L" | grep -q "ROADMAP.md:[4-7]:" && for n in 4 6 7; do echo "$Hs" | grep -q "Project-Foo/ROADMAP.md:$n:" || exit 1; done && echo "$Hs" | grep -q "FILE-OWNERSHIP.md:3:" && echo "$Hs" | grep -q "Foo-HQ/agent-TODO.md:4:" && ! grep -q "ROADMAP.md:5:" "$T/out" && ! grep -q "decisions\|MISTAKES\|episodic\|run.log\|x.jsonl\|inbox.md:\|_example-agent" "$T/out" )'
ok "1d plan: who gets letters, 2 identities, the live tab named" 'grep -q "to: Bar-Dev, Foo-Dev, Foo-DevOps, Foo-HQ, Foo-OpsX, Keeper$" "$T/out" && grep -q "identity: 2 session" "$T/out" && grep -q "live tab: workspace-7" "$T/out"'

rc=$(run Foo-Ops Foo-DevOps --apply); N="$A/Foo-DevOps"
ok "2 apply: rc 0, the folder moved, the old one gone, content intact" '[ "$rc" = 0 ] && [ ! -e "$A/Foo-Ops" ] && [ -f "$N/briefing.md" ] && [ "$(cat "$N/Foo-Ops-notes.md")" = note ]'
ok "2b .aliases has the old name" 'grep -qx Foo-Ops "$N/.aliases"'
ok "2c old-style todo files renamed, other files not" '[ -f "$N/Foo-DevOps-agent-TODO.md" ] && [ -f "$N/Foo-DevOps-human-TODO.md" ] && [ ! -e "$N/Foo-Ops-agent-TODO.md" ] && [ -f "$N/Foo-Ops-notes.md" ]'
ok "3 identities: both (one with a trailing slash) -> the new folder, the other agent intact" '[ "$(cat "$I/s-live")" = "$N" ] && [ "$(cat "$I/s-slash")" = "$N" ] && [ "$(cat "$I/s-x")" = "$A/Foo-OpsX" ]'
ok "3b alarm mode moved with its value, the other one intact" '[ "$(cat "$T/mode/Foo-DevOps")" = auto ] && [ ! -e "$T/mode/Foo-Ops" ] && [ "$(cat "$T/mode/Foo-OpsX")" = off ]'
ok "3c live tab -> a restart warning" 'grep -q "live tab: workspace-7 (pid $$" "$T/out" && grep -q "restart the tab" "$T/out"'
ok "4 work-guard list: the line replaced, Foo-OpsX and the comment intact" '[ "$(cat "$T/wga")" = "$(printf "# comment Foo-Ops\nFoo-HQ\nFoo-DevOps\nFoo-OpsX")" ]'
ok "4b release.toml: Bar hq = Foo-DevOps, Foo unchanged" 'grep -qx "hq = \"Foo-DevOps\"" "$R/Project-Bar/release.toml" && grep -qx "hq = \"Foo-HQ\"" "$R/Project-Foo/release.toml"'
ok "4c AGENTS.md: row and path updated with the old name noted, Foo-OpsX intact" 'grep -qF "| Foo-DevOps (renamed from Foo-Ops on $(date +%F)) | DevOps of Foo | other projects | \`Agents/Foo-DevOps/briefing.md\` |" "$R/AGENTS.md" && grep -qF "| **Foo-OpsX** | other | - | \`Agents/Foo-OpsX/briefing.md\` |" "$R/AGENTS.md"'
ok "5 ROADMAP: the Lead header replaced, the rest (history, [D], substrings) byte for byte" 'grep -qxF "> Lead: Foo-HQ, deploys - Foo-DevOps. Legend: done · active" "$R/Project-Foo/ROADMAP.md" && [ "$(sed 3d "$R/Project-Foo/ROADMAP.md")" = "$(printf "# Foo - roadmap\n\n- E1.S1 owner **Foo-Ops** (since 22.10).\n- E1.S2 Foo-OpsX and xFoo-Ops and Foo-Ops-Legacy - leave alone\n- E1.S3 a letter in Agents/Foo-Ops/inbox.md, end of sentence Foo-Ops.\n- [D] the human 2026-11-22 10:53 (in the Foo-Ops tab): yes")" ]'
ok "5a whole word in a live briefing: with **, in a path, at the end of a sentence - yes; substring and dash continuation - no" 'grep -qxF "owner **Foo-DevOps**, a letter in Agents/Foo-DevOps/inbox.md; Foo-OpsX and xFoo-Ops and Foo-Ops-Legacy - leave alone" "$A/Other/briefing.md"'
ok "5b FILE-OWNERSHIP, OWNERS, another briefing, a group briefing, its own briefing (path and todo name)" 'grep -qF "**Foo-DevOps** |" "$R/Project-Foo/FILE-OWNERSHIP.md" && grep -qxF -- "- [D] 2026-10-22 Foo-Ops took deploys" "$R/Project-Foo/FILE-OWNERSHIP.md" && grep -qF "| Other | Foo-OpsX |" "$R/Project-Foo/FILE-OWNERSHIP.md" && [ "$(cat "$R/Project-Foo/OWNERS")" = "$(printf "deploy/** Foo-DevOps\nweb/** Foo-OpsX")" ] && grep -qx "Deploy questions go to Foo-DevOps\." "$A/Other/briefing.md" && grep -q "Neighbour: Foo-DevOps " "$A/Grp/Grp-View/briefing.md" && grep -qxF "Briefing: Agents/Foo-DevOps/briefing.md · todo: Foo-DevOps-agent-TODO.md" "$N/briefing.md"'
ok "5c the team todo replaced, a non-team todo (Solo) not" 'grep -q "waiting for Foo-DevOps" "$A/Foo-HQ/agent-TODO.md" && grep -q "Foo-Ops has not done it yet" "$A/Solo/agent-TODO.md"'
ok "5d rewritten files: owner, group and mode kept, no temp files left" '[ "$(own "$A/Other/briefing.md")" = "$own0" ] && [ -z "$(find "$T" -name ".rename-agent.*")" ]'
ok "5e history outside the list (decisions, MISTAKES, episodic, *.log, *.jsonl, a non-team inbox, the template folder) unchanged" '[ "$(hist)" = "$hs0" ]'
ok "5f todo: the Done section kept, the live sections before and after replaced" '[ "$(cat "$A/Foo-HQ/agent-TODO.md")" = "$(printf "## Open\n- [ ] waiting for Foo-DevOps\n## Done\n- [x] letter from Foo-Ops closed\n## Next\n- [ ] ask Foo-DevOps")" ]'
ok "6 letters through inbox_post.sh: exactly the team (Foo-HQ, Foo-Dev, Foo-OpsX by prefix, Bar-Dev, Keeper - Bar lead, Foo-DevOps itself), not Solo/Other" '[ "$(got Foo-Ops Foo-DevOps)" = "Bar-Dev Foo-Dev Foo-DevOps Foo-HQ Foo-OpsX Keeper " ] && grep -q "^- \[ \] \[" "$A/Foo-HQ/inbox.md"'
cp -r "$A" "$T/agents0"
rc=$(run Foo-Ops Foo-DevOps --apply); ok "7 repeat -> rc 4 (old is gone), no letters added" '[ "$rc" = 4 ] && diff -rq "$A" "$T/agents0" >/dev/null'
rm -rf "$T/agents0"
h1=$(snap); rc=$(run Solo Foo-HQ --apply); ok "8 new already exists -> rc 4, nothing changed" '[ "$rc" = 4 ] && [ "$(snap)" = "$h1" ] && grep -q "already exists" "$T/out"'
rc=$(run Solo Grp-View --apply); ok "8b new exists in a group folder -> rc 4" '[ "$rc" = 4 ] && [ "$(snap)" = "$h1" ]'
rc=$(run Solo ops-old --apply); ok "8c new is an alias of another agent (.aliases, any case) -> rc 4" '[ "$rc" = 4 ] && grep -q "alias" "$T/out" && [ "$(snap)" = "$h1" ]'
rc=$(run Ghost New1); ok "8d old missing -> rc 4" '[ "$rc" = 4 ]'
rc=$(run Grp NewGrp --apply); ok "8e group folder without briefing.md -> rc 4" '[ "$rc" = 4 ] && [ -d "$A/Grp" ]'
rc=$(run Solo); ok "9 one argument -> rc 2" '[ "$rc" = 2 ]'
rc=$(run Solo 'a/b'); ok "9b new with \"/\" -> rc 2" '[ "$rc" = 2 ]'
rc=$(run Solo Solo); ok "9c the same name -> rc 2" '[ "$rc" = 2 ]'
rc=$(run Solo X --force); ok "9d unknown flag -> rc 2" '[ "$rc" = 2 ] && [ "$(snap)" = "$h1" ]'
rc=$(env -u CCM_WORKSPACE bash "$RA" Solo X > "$T/out" 2>&1; echo $?); ok "9e CCM_TEST without CCM_WORKSPACE in env -> rc 2 (the real root untouched)" '[ "$rc" = 2 ] && grep -q CCM_WORKSPACE "$T/out" && [ "$(snap)" = "$h1" ]'
rc=$(run Grp-View Grp-Eye --apply); ok "10 an agent in a group folder: Agents/Grp/Grp-View -> Agents/Grp/Grp-Eye" '[ "$rc" = 0 ] && [ -f "$A/Grp/Grp-Eye/briefing.md" ] && [ ! -e "$A/Grp/Grp-View" ] && grep -qx Grp-View "$A/Grp/Grp-Eye/.aliases"'
rc=$(run Solo Solo2 --apply); ok "11 outside a project: rc 0, no letters, todo name clash -> both kept with a warning" '[ "$rc" = 0 ] && [ -z "$(got Solo Solo2)" ] && grep -q "outside Project-\*" "$T/out" && [ "$(cat "$A/Solo2/Solo2-agent-TODO.md")" = "- [ ] already a new one" ] && [ -f "$A/Solo2/Solo-agent-TODO.md" ] && grep -q "! Solo-agent-TODO.md" "$T/out"'
ok "11b no row in AGENTS.md -> a warning, not a failure" 'grep -q "no row for \"Solo\"" "$T/out"'
# a letter that cannot be delivered -> rc 6, everything else done
mkdir -p "$R/Project-Zed" "$A/Zed-HQ" "$A/Zed-Dev"; echo "# Zed-HQ" > "$A/Zed-HQ/briefing.md"; echo "# Zed-Dev" > "$A/Zed-Dev/briefing.md"
printf '# Zed-Dev - inbox\n\n## New\n\n## Processed\n' > "$A/Zed-Dev/inbox.md"; printf 'hq = "Zed-HQ"\n' > "$R/Project-Zed/release.toml"
rc=$(run Zed-Dev Zed-Ops --apply); ok "12 Zed-HQ has no inbox -> rc 6, the rename done, the letter to Zed-Ops arrived" '[ "$rc" = 6 ] && [ -f "$A/Zed-Ops/briefing.md" ] && grep -q "letter to Zed-HQ did not arrive" "$T/out" && [ "$(got Zed-Dev Zed-Ops)" = "Zed-Ops " ]'
# Ukrainian markers only with CCM_LANG_EXTRA=uk
mkdir -p "$R/Project-Uk" "$A/Uk-HQ" "$A/Uk-Old"
for b in Uk-HQ Uk-Old; do echo "# $b" > "$A/$b/briefing.md"; printf '# %s - inbox\n\n## New\n\n## Processed\n' "$b" > "$A/$b/inbox.md"; done
printf '# Uk\n\n> Штаб: Uk-HQ, деплой — Uk-Old. Легенда\n- Uk-Old робить\n' > "$R/Project-Uk/ROADMAP.md"
printf '## Відкрите\n- [ ] спитати Uk-Old\n- [Р] Uk-Old узяв\n## Оброблено\n- [x] від Uk-Old\n' > "$A/Uk-HQ/agent-TODO.md"
rc=$(CCM_LANG_EXTRA=uk run Uk-Old Uk-New --apply); ok "13 uk: the Штаб header replaced, [Р] and Оброблено kept, the team found by Штаб" '[ "$rc" = 0 ] && grep -qxF "> Штаб: Uk-HQ, деплой — Uk-New. Легенда" "$R/Project-Uk/ROADMAP.md" && grep -qxF -- "- Uk-Old робить" "$R/Project-Uk/ROADMAP.md" && [ "$(cat "$A/Uk-HQ/agent-TODO.md")" = "$(printf "## Відкрите\n- [ ] спитати Uk-New\n- [Р] Uk-Old узяв\n## Оброблено\n- [x] від Uk-Old")" ] && [ "$(got Uk-Old Uk-New)" = "Uk-HQ Uk-New " ]'
echo "rename-agent: $pass pass, $fail fail"; [ $fail = 0 ]
