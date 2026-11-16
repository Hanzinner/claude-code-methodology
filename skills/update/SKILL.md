---
name: update
description: Update the installed methodology (hooks, rules, scripts, skills) from its git repo, tell the person in plain words what is new, reinstall the same way, merge CLAUDE.md if needed, check. Use when the user says "/update", "update the system", "update yourself", "pull the new version" (in any language). Not for updating Claude Code itself (that is `claude update`).
---

# update

The person wants the new version of the system they installed. Do the whole thing; they should only have to read
what is new and restart.

If the person only said "update" and it is not clear whether they mean this system or Claude Code itself, ask one
line: "the system (rules, hooks, commands) or Claude Code itself?". Claude Code itself: `claude update`.

## Steps

1. **Where it came from.** Read `~/.claude/.methodology-installed/source` (for a project install:
   `<project>/.claude/.methodology-installed/source`): `repo=` (the clone), `commit=` (the installed version),
   `scope=` (`user` or `project`), `project=`. No file (installed before this command existed): the repo is
   `~/claude-code-methodology`, the installed version is that clone's current `HEAD`, scope `user`.
2. **Get the new version.** In the repo: `git pull --ff-only`. If it refuses (local changes, a diverged
   branch), stop and show the person the message; do not reset or stash anything yourself.
   Nothing new (`HEAD` equals the installed commit) → say "already up to date" and stop.
3. **What is new, for a person.** `git log --format='%s%n%b' <installed commit>..HEAD` and
   `git diff <installed commit>..HEAD -- docs/getting-started.md README.md`. Tell the person only what changes
   something for them, at most about seven lines, each as the problem it removes, then what it does, then how to
   use it; a tool's name only after that. Skip internal fixes, tests and refactoring, or sum them up in one line
   ("plus N fixes inside"). A new optional add-on: say what they would get from it and the flag, and ask whether
   they want it.
4. **Install the same way.** `./install.sh --user` (or `--project <dir>` from step 1), plus any add-on flag the
   person just asked for. It keeps their memory, settings, own hooks and CLAUDE.md edits.
5. **Check.** `./check-install.py --user` (or `--project <dir>`). Not done until it ends with
   "0 missing or broken"; fix and re-run.
6. **CLAUDE.md.** If the install left `CLAUDE.md.new` and `CLAUDE.md.changes` next to the person's own
   `CLAUDE.md`, merge by meaning: keep everything of theirs, add what is new in `CLAUDE.md.changes`, ask one line
   about each new rule that contradicts theirs. Then mark it merged as the installer said
   (`mv CLAUDE.md.new .methodology-installed/CLAUDE.md.base`) and run the check again.
7. **Tell them to restart Claude Code**: a running session does not pick up new hooks.

Never delete or move anything in `~/.claude` yourself beyond step 6. Keys never go into the chat.
