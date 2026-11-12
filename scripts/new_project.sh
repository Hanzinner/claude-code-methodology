#!/usr/bin/env bash
# new_project.sh (--own-repo [--profile web|game|tool] | --no-code) <Name> [<agent>...] - start a project with one command.
# What is useful across projects is carried by a tool, not by text: the next project gets the same skeleton for free.
# Default agents: <Name>-HQ <Name>-Dev (the first one is the project lead). The repo choice is EXPLICIT (one of the two flags is
# required): a project of its own repo only when it really is a code project; without code it is a folder in the shared repo and
# the snapshot job picks its files up. (A lead once read --own-repo as an option and got a project without a release queue.)
# Does: release.toml · ROADMAP.md · BLOCKERS.md · first commit (own repo) · agent folders (briefing, inbox, todo) ·
# the optional lists below · the workspace .gitignore entry for a repo of its own.
# The gate command and `releaser.py approve <Name>` are filled in by the project lead: an empty `test` is reported by the
# releaser in its state file and turned red by project_drift.py.
# --profile sets the stands: web test/uat/prod · game dev-build/playtest · tool test/prod (without the flag: empty).
# Any step failing -> stop, naming the step; what was already created stays and is printed. exit: 0 ok · 2 usage · 3 already exists · 4 a step failed.
# Settings (methodology.conf or env): CCM_WORKSPACE, CCM_AGENTS_DIR, CCM_PROJECTS_GLOB (default Project-*), and these optional ones,
# empty = the step is skipped:
#   CCM_REGISTER_AGENT       an executable that creates one agent (called with the agent name); empty = built-in scaffold
#   CCM_PROJECT_WATCH_DOCS   space-separated docs added to every new agent's .watchlist (e.g. a team-work doc)
#   CCM_PROJECT_WATCH_DOCS_HQ  the same, for the lead only
#   CCM_WORK_GUARD_AGENTS    a file with one agent per line (an "alarm" list); new agents are appended
#   CCM_PROJECTS_SITE        a local address of a projects page; only mentioned in the final message
# A lead agent created in advance is attached, not refused (its briefing and todo are not touched).
# Test: tests/new-project-test.sh
set -euo pipefail
export LC_ALL=C.UTF-8
HERE=$(dirname "$(readlink -f "$0")")
eval "$(python3 "$HERE/../lib/ccm_conf.py" --shell)"
conf_get() { python3 "$HERE/../lib/ccm_conf.py" "$1"; }
REPO=$CCM_WORKSPACE
AGENTS_DIR=$CCM_AGENTS_DIR
GLOB=${CCM_PROJECTS_GLOB:-$(conf_get CCM_PROJECTS_GLOB)}; GLOB=${GLOB:-Project-*}
PREFIX=${GLOB%%\**}
REG=${CCM_REGISTER_AGENT:-$(conf_get CCM_REGISTER_AGENT)}
DOCS=${CCM_PROJECT_WATCH_DOCS:-$(conf_get CCM_PROJECT_WATCH_DOCS)}
DOCS_HQ=${CCM_PROJECT_WATCH_DOCS_HQ:-$(conf_get CCM_PROJECT_WATCH_DOCS_HQ)}
WGA=${CCM_WORK_GUARD_AGENTS:-$(conf_get CCM_WORK_GUARD_AGENTS)}
SITE=${CCM_PROJECTS_SITE:-$(conf_get CCM_PROJECTS_SITE)}
step="preparation"
trap 'rc=$?; echo "FAILED at step \"$step\" (rc=$rc). What was created stays: ${P:-}; remove it or finish by hand." >&2; exit 4' ERR

# whoever owns the workspace owns the new files; run as that user when we are root (a root-owned file in a user's repo breaks it)
OWNER=$(stat -c %U "$REPO")
if [[ "$(id -u)" == 0 && "$OWNER" != root ]]; then AS=(runuser -u "$OWNER" --); else AS=(); fi
ogit() { "${AS[@]}" git -c safe.directory='*' "$@"; }
chown_owner() { [[ ${#AS[@]} -gt 0 ]] && chown -R "$OWNER:$(stat -c %G "$REPO")" "$@" || true; }

own=0; nocode=0; stands=""
while [[ "${1:-}" == --* ]]; do
    case "$1" in
        --own-repo) own=1; shift ;;
        --no-code) nocode=1; shift ;;
        --profile) case "${2:-}" in
                       web)  stands='"test", "uat", "prod"' ;;
                       game) stands='"dev-build", "playtest"' ;;
                       tool) stands='"test", "prod"' ;;
                       *) echo "--profile web|game|tool" >&2; exit 2 ;;
                   esac; shift 2 ;;
        *) echo "unknown flag $1" >&2; exit 2 ;;
    esac
done
if (( own == nocode )); then
    echo "say explicitly: a project with code -> --own-repo --profile web|game|tool; without code -> --no-code (a folder in the shared repo)" >&2; exit 2
fi
name=${1:-}; [[ $# -ge 1 ]] && shift
[[ "$name" =~ ^[A-Za-z][A-Za-z0-9-]{0,30}$ ]] || { echo "new_project.sh (--own-repo|--no-code) <Name in Latin letters> [<agent>...]" >&2; exit 2; }
agents=("$@"); [[ ${#agents[@]} -gt 0 ]] || agents=("$name-HQ" "$name-Dev")
hq=${agents[0]}
P="$PREFIX$name"; D="$REPO/$P"
[[ ! -e "$D" ]] || { echo "$D already exists: doing nothing" >&2; exit 3; }
# A lead created in advance (from a conversation) is attached, not refused. Any other existing agent is a refusal.
hq_exists=0
for a in "${agents[@]}"; do
    if [[ -e "$AGENTS_DIR/$a" ]]; then
        # its own, not somebody else's: no project has it as its lead yet (grep hq in every release.toml)
        if [[ "$a" == "$hq" && -f "$AGENTS_DIR/$a/briefing.md" ]] && ! grep -qsxF "hq = \"$a\"" "$REPO"/$GLOB/release.toml; then
            hq_exists=1; continue; fi
        echo "agent $a already exists: pick another name or attach it by hand" >&2; exit 3
    fi
done

step="project folder"
mkdir "$D"; chown_owner "$D"
if (( own )); then
    step="repo (git init)"
    ogit -C "$D" init -q -b master
    [[ -e "$D/.git" ]] || { echo "git init did not create $D/.git" >&2; false; }
    step="top-level .gitignore"      # the workspace repo must not track a nested repo
    touch "$REPO/.gitignore"
    grep -qxF "/$P/" "$REPO/.gitignore" || printf '/%s/\n' "$P" >> "$REPO/.gitignore"
fi

step="project files"
cat > "$D/release.toml" <<E
# The project file for the release queue (scripts/releaser.py). After changing the commands: releaser.py approve $name
hq = "$hq"
test = ""            # put the gate command here; it runs as the separate releaser user
stands = [$stands]
E
cat > "$D/ROADMAP.md" <<E
# $name - roadmap

> Lead: $hq. Legend: done · active · waiting · far. A story with a blocker: \`blockers: B<n>\`.

## EPIC 1
E
cat > "$D/BLOCKERS.md" <<E
# BLOCKERS - $P

What blocks a story and waits for the human or an outside party. One row per blocker.
E
chown_owner "$D/release.toml" "$D/ROADMAP.md" "$D/BLOCKERS.md"

if (( own )); then
    step="first commit"
    ogit -C "$D" add release.toml ROADMAP.md BLOCKERS.md
    if [[ -z "$(ogit -C "$D" config user.name || true)" ]]; then id_args=(-c user.name="Project Bot" -c user.email=bot@localhost); else id_args=(); fi
    ogit -C "$D" "${id_args[@]}" commit -qm "$P: skeleton (new_project.sh)"
fi

# ---- agents: a registrar hook, or the built-in scaffold from swarm-template/Agents/_example-agent
scaffold() {   # scaffold <agent> <lead|member>
    local a=$1 ad="$AGENTS_DIR/$1"
    mkdir -p "$ad"
    cat > "$ad/briefing.md" <<E
# $a - briefing

> Role in one line: $( [[ "$2" == lead ]] && echo "the lead of project $name" || echo "works in project $name" ).
> Read first: $D/ROADMAP.md

## Owns
- The files and domains of project $name that the lead assigns (the lead keeps $D/OWNERS if there is one).

## Doesn't touch
- Shared mechanisms and other projects' files. A change there -> a letter to the owner.

## How it works
- Tasks come from the inbox and the project roadmap. Work in your own git worktree; deliver through the release queue.

<!-- Self-healing: an instruction here didn't work as written and you found a working way -> append a dated
     line at the bottom: what didn't work · why · the fix. Append, don't rewrite. -->
E
    printf '# %s - inbox\n\n## New\n\n## Done\n' "$a" > "$ad/inbox.md"
    printf '# %s - open loops\n\n## Open\n\n## Closed\n' "$a" > "$ad/agent-TODO.md"
    printf '# %s - waiting for the human\n\n## Open\n\n## Closed\n' "$a" > "$ad/human-TODO.md"
    if [[ -f "$REPO/AGENTS.md" ]] && ! grep -q "| $a |" "$REPO/AGENTS.md"; then
        printf '| %s | project %s | other projects, shared mechanisms | `Agents/%s/briefing.md` |\n' "$a" "$name" "$a" >> "$REPO/AGENTS.md"
    fi
    chown_owner "$ad"
}
step="agents"
for a in "${agents[@]}"; do
    role=member; [[ "$a" == "$hq" ]] && role=lead
    if (( hq_exists )) && [[ "$a" == "$hq" ]]; then echo "lead $a already exists - attaching, briefing untouched"
    elif [[ -n "$REG" ]]; then "$REG" "$a" > /dev/null
    else scaffold "$a" "$role"; fi
    if [[ -n "$DOCS$DOCS_HQ" ]]; then
        wl="$AGENTS_DIR/$a/.watchlist"
        list=($DOCS); [[ "$a" == "$hq" ]] && list+=($DOCS_HQ)
        for doc in "${list[@]}"; do grep -qxF "$doc" "$wl" 2>/dev/null || echo "$doc" >> "$wl"; done
    fi
done

if [[ -n "$WGA" ]]; then
    step="alarm list ($WGA)"
    new=(); for a in "${agents[@]}"; do grep -qxF "$a" "$WGA" 2>/dev/null || new+=("$a"); done
    if [[ ${#new[@]} -gt 0 ]]; then
        printf '# %s (new_project.sh %s)\n' "$name" "$(date +%F)" >> "$WGA"
        printf '%s\n' "${new[@]}" >> "$WGA"
    fi
fi

step="commit of the top-level .gitignore"
if (( own )) && [[ -d "$REPO/.git" || -f "$REPO/.git" ]] && ! ogit -C "$REPO" diff --quiet -- .gitignore; then
    if [[ -z "$(ogit -C "$REPO" config user.name || true)" ]]; then id_args=(-c user.name="Project Bot" -c user.email=bot@localhost); else id_args=(); fi
    ogit -C "$REPO" "${id_args[@]}" commit -qm "$P - repo of its own (new_project.sh)" -- .gitignore
fi

echo "ok $P: $( (( own )) && echo "repo of its own" || echo "folder in the shared repo"), release.toml, ROADMAP, BLOCKERS; agents: ${agents[*]}"
echo "Next for the lead $hq: put the gate command into release.toml and run: releaser.py approve $name. To bring an agent up, write its name as the first message of a chat."
[[ -z "$SITE" ]] || echo "The projects page at $SITE picks up ROADMAP.md by itself."
