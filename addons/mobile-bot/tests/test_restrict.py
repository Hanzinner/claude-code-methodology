#!/usr/bin/env python3
"""Acceptance test of the mobile gate: one fixture = one rule. Runs the real hook entry point
in a throwaway HOME. Prints how many cases ran; fails loudly on any wrong verdict."""
import json, os, pathlib, subprocess, sys, tempfile

HOOK = pathlib.Path(__file__).resolve().parent.parent / "hooks" / "mobile-restrict.sh"
tmp = os.path.realpath(tempfile.mkdtemp())
home, work = f"{tmp}/home", f"{tmp}/work"
os.makedirs(f"{home}/.ssh"); os.makedirs(work)


def run(payload, raw=None, bot="1", allow=None):
    env = {**os.environ, "HOME": home, "CLAUDE_MOBILE_BOT": bot,
           "CLAUDE_MOBILE_BOT_ALLOW_PATHS": allow or f"{work}/notes"}
    inp = raw if raw is not None else json.dumps({"cwd": work, **payload})
    return subprocess.run(["bash", str(HOOK)], input=inp, env=env, capture_output=True, text=True).returncode


def bash(c): return {"tool_name": "Bash", "tool_input": {"command": c}}
def write(p): return {"tool_name": "Write", "tool_input": {"file_path": p}}
def read(p): return {"tool_name": "Read", "tool_input": {"file_path": p}}


ALLOW = [bash(c) for c in ('grep -rn foo .', 'grep -A 3 foo x.md', 'grep --include="*.md" -r foo .', 'tail -5 x', 'head -n 5 x',
                           'date +%F', 'date -u', 'git diff --stat', 'git show HEAD~1', 'git log -n 3 --since=2026-01-01', 'du -sh .',
                           'stat x', 'which python3', 'sort -k2 -n x', 'wc -l x', 'df -h', 'pwd', 'whoami', 'echo .ssh',
                           'grep credential x.md', 'grep -e .env x.md', 'grep "a*b?" x.md', 'ls -la', 'grep -i foo x.md', 'grep "a;b" x.md', 'cat a.md | head -20', 'sort x | uniq -c',
                           'sort -u x', 'git log --oneline -5', 'tree -L 2', 'echo hello')]
ALLOW += [write(f"{work}/notes/a.md"), read(f"{work}/a.md"),
          {"tool_name": "Grep", "tool_input": {"path": work, "pattern": "a..b"}}]
DENY = [bash(c) for c in ('ls\nrm x', 'ls\rrm x', 'cat a > b', 'cat a < b', 'ls; rm x', 'ls && rm x', 'ls & rm x', 'ls || rm x',
                          'cat <(id)', 'echo $HOME', 'echo `id`', 'echo "unclosed', 'rm x', 'python3 x.py', 'tee x',
                          'sed -i s/a/b/ x', 'find . -delete', 'sort -o out in', 'sort -oout in', 'tree -o out',
                          'uniq in out', 'date -s 2020-01-01', 'git checkout x', 'git -C / status',
                          'git diff --output=x', 'cat ~/.ssh/id_ed25519', 'grep -r token ~', 'cat /proc/self/environ', ' ',
                          'cat ~/.ss[h]/config', 'cat ~/.ss?/config', 'cat ~/.ssh/*', 'grep -f ~/.ssh/config x.md',
                          'grep --file ~/.ssh/config x.md', 'grep -if ~/.ssh/config x.md', 'grep "" ~/.ssh/config',
                          'grep -e foo ~/.ssh/config', 'grep -f.env x.md', 'head -n1 ~/.ssh/config',
                          'grep -f x.md ~/.ssh/config', 'cat ~/.netrc', 'cat ~/.aws/config',
                          # flag allowlist: each of these got past the old forbidden-flag list
                          'cat a.md | uniq - x.out', 'sort -uo x.out a', 'sort --outp=x.out a', 'sort -S 1 --compress-program=sh a',
                          'sort -T /tmp a', 'tree -ao out', 'grep --file=a.md ~/.ssh/config', 'grep -d recurse TOKEN ~',
                          'grep --directories=recurse TOKEN ~', 'grep --recur TOKEN ~', 'grep -R x .', 'date -f../x', 'file -f../x',
                          'du -X../x', 'git diff -O../x', 'git diff --outp=x', 'git diff --ext-diff', 'date 0101', 'tail -f x',
                          'git log --pretty x', 'git show HEAD:.env', 'cat ~-/.ssh/config', 'cat ~+/x', 'cat ~root/x', 'ls --recur ~',
                          'cat ~/.claude.json', 'cat ~/.claude/history.jsonl', 'cat ~/.claude/backups/x', 'cat ~/.git-credentials',
                          'cat ~/.docker/config.json', 'cat /etc/sudoers.d/x', 'stat ~/.ssh/config', 'cat ~/.s{s,}h/config',
                          r'cat ~/.ss\h/config', "cat ~/.ss''h/config", 'grep -f~/.ssh/config x.md', 'git diff --no-index /dev/null ~/.ssh/config')]
DENY += [write(f"{work}/other/a.md"), write(f"{work}/notes/id_rsa.PEM"), write(f"{work}/notes/.ENV"),
         write(f"{work}/notes/.git/config"), write(""), write(f"{work}/notes/CLAUDE.md"), write(f"{work}/notes/.claude/agents/a.md"), read(f"{home}/.ssh/config"), read(f"{work}/.env"),
         {"tool_name": "Grep", "tool_input": {"path": home, "pattern": "x"}},
         {"tool_name": "Glob", "tool_input": {"pattern": "/etc/*"}}]

bad = [("allow", p) for p in ALLOW if run(p) != 0] + [("deny", p) for p in DENY if run(p) != 2]
# Own code is protected even when the allowlist covers it: this fixture tests only that rule.
addon = str(HOOK.parent.parent)
for f in (HOOK.parent / "mobile_restrict.py", HOOK.parent.parent / "bot.py"):
    if run(write(str(f)), allow=addon) != 2: bad.append(("deny", f"own code {f.name}"))
# Recursive tools without a path walk the working dir: run from HOME, an ancestor of the zones.
for c in ("grep -r token", "ls -R", "tree", "du"):
    if run({**bash(c), "cwd": home}) != 2: bad.append(("deny", f"{c} from HOME"))
if run({"tool_name": "Grep", "tool_input": {"pattern": "x"}, "cwd": home}) != 2: bad.append(("deny", "Grep from HOME"))
if run(None, raw="not json") != 2: bad.append(("deny", "garbage stdin"))     # fail-closed
if run(bash("rm x"), bot="") != 0: bad.append(("allow", "outside the bot"))  # no-op
# [SEND:] shares the gate's definition of "secret"
sys.path.insert(0, str(HOOK.parent)); os.environ["HOME"] = home
from mobile_restrict import refuse_send
for p in (f"{work}/.env", f"{work}/id_rsa", f"{work}/a.pem", f"{work}/.git/config"):
    if not refuse_send(p): bad.append(("refuse send", p))
if refuse_send(f"{work}/report.pdf"): bad.append(("allow send", "report.pdf"))
total = len(ALLOW) + len(DENY) + 2 + 5 + 2 + 5
for want, p in bad: print(f"WRONG, wanted {want}: {p}")
print(f"{total} cases, {len(bad)} wrong")
sys.exit(1 if bad or total < 100 else 0)
