#!/usr/bin/env bash
# Test of mech_snapshot.sh in a sandbox tree (temp HOME, temp git dir, fake letter command). Nothing real is touched.
# The fake secret is assembled from parts: this file contains nothing that looks like a secret.
# M=<path> tests another copy.
set -u
HERE="$(dirname "$(readlink -f "$0")")"
M=${M:-$HERE/../scripts/mech_snapshot.sh}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export HANZ_TEST=1 HOME="$T/home" CLAUDE_METHODOLOGY_CONF=/nonexistent
mkdir -p "$HOME"
W="$T/code"; mkdir -p "$W/scripts" "$W/hooks"
for i in $(seq 1 12); do printf '#!/bin/bash\necho %s\n' "$i" > "$W/scripts/s$i.sh"; done
printf '#!/bin/bash\n' > "$W/hooks/h.sh"
SCAN="$HERE/../bin/secret-scan"; [ -x "$SCAN" ] || SCAN="$(dirname "$M")/../bin/secret-scan"
cat > "$T/post" <<'EOP'
#!/bin/bash
echo "$1 :: $2" >> "$(dirname "$0")/posted"
EOP
chmod +x "$T/post"
WL=$'scripts/*.sh\nhooks/*'
run() { (cd "$W/scripts" 2>/dev/null || cd "$T"; env CCM_WORKSPACE="$T/ws" CCM_CLAUDE_DIR="$W" MECH_WHITELIST="${WLX:-$WL}" MECH_GIT_DIR="$T/mech.git" MECH_WORK_TREE="$W" MECH_LOG="$T/log" MECH_POST="$T/post" MECH_OWNER=owner MECH_SECRET_SCAN="$SCAN" bash "$M" >/dev/null 2>&1; echo $?); }
gl() { /usr/bin/env git --git-dir="$T/mech.git" --work-tree="$W" "$@"; }
FAKE="gh""p_$(printf 'B%.0s' $(seq 36))"
pass=0; fail=0
ok() { if eval "$2"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $1"; tail -3 "$T/log"; fi; }

printf 'T=%s\n' "$FAKE" > "$W/scripts/first-leak.sh"
rc=$(run); ok "0 secret already in the FIRST snapshot (no HEAD): taken out, the rest committed" '[ "$rc" = 0 ] && ! gl ls-files | grep -q first-leak.sh && gl ls-files | grep -q s1.sh'
rm "$W/scripts/first-leak.sh"; rm -rf "$T/mech.git"; : > "$T/posted"
rc=$(run); ok "1 first snapshot: rc 0, 13 files in the commit" '[ "$rc" = 0 ] && [ "$(gl ls-files | wc -l)" = 13 ]'
ok "1b run from a cwd inside the tree (as cron): files are IN the commit, not only in the index" '[ "$(gl ls-tree -r --name-only HEAD | grep -c "^scripts/")" = 12 ]'
rc=$(run); ok "2 no changes: rc 0, no new commit" '[ "$rc" = 0 ] && [ "$(gl rev-list --count HEAD)" = 1 ]'
echo 'echo changed' >> "$W/scripts/s1.sh"; printf 'T=%s\n' "$FAKE" > "$W/scripts/leak.sh"
rc=$(run); ok "3 a change + a file with a secret: the change is committed, the secret is not" '[ "$rc" = 0 ] && gl show --stat HEAD | grep -q s1.sh && ! gl ls-files | grep -q leak.sh'
ok "3b letter to the owner about the secret, the value is not in it" 'grep -q "^owner :: .*leak.sh" "$T/posted" && ! grep -qF "$FAKE" "$T/posted" "$T/log"'
rm "$W/scripts/leak.sh" "$W/scripts/s12.sh"
rc=$(run); ok "4 a deleted file leaves the index at the next snapshot, history keeps it" '[ "$rc" = 0 ] && ! gl ls-files | grep -q s12.sh && gl log --all --name-only --format= | grep -q s12.sh'
printf 'T=%s\n' "$FAKE" > "$W/scripts/manual.sh"
(cd "$W" && gl add scripts/manual.sh && gl commit -qm manual) >/dev/null 2>&1; mrc=$?
ok "5 a manual commit of a secret around the script -> pre-commit rejects it" '[ "$mrc" != 0 ] && ! gl log --name-only --format= | grep -q manual.sh'
gl reset -q; rm "$W/scripts/manual.sh"
: > "$T/posted"; rm -f "$T"/.mech-alert-*
rc=$(WLX="$WL"$'\nlib/*' run)
ok "6a a pattern without files -> rc 3, the letter names exactly it" '[ "$rc" = 3 ] && grep -q "lib/\*" "$T/posted" && ! grep -q "scripts/\*.sh" "$T/posted"'
n1=$(wc -l < "$T/posted"); rc=$(WLX="$WL"$'\nlib/*' run)
ok "6b the same letter is not sent twice a day" '[ "$(wc -l < "$T/posted")" = "$n1" ]'
rc=$(WLX="scripts/*.sh" MECH_MIN_FILES=50 run)
ok "6c fewer files than MECH_MIN_FILES -> rc 3 (broken instrument, no false green)" '[ "$rc" = 3 ]'
rc=$(WLX="$WL"$'\n'"${T#/}/ws/*.md" run)
ok "7 a whitelist pattern under the workspace -> refusal rc 4" '[ "$rc" = 4 ] && grep -q REFUSE "$T/log"'
mv "$W/scripts" "$T/scripts-hidden"; : > "$T/posted"; rm -f "$T"/.mech-alert-*
rc=$(run); ok "8 empty whitelist -> rc 3 + alert" '[ "$rc" = 3 ] && grep -q "mech_snapshot" "$T/posted"'
echo "mech-snapshot: $pass pass, $fail fail"; [ $fail = 0 ]
