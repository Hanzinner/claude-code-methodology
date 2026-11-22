#!/usr/bin/env bash
# Bootstrap installer for claude-code-methodology.
#
# Detects Claude Code, asks where to install (user vs project scope),
# copies hooks/scripts/skills with path-rewriting, generates settings.json,
# offers optional Python deps, offers optional add-ons (mobile-bot, offsite-backup, agent-browser, net-change, dashboard — each only with its flag).
#
# Usage:
#   ./install.sh                 # interactive
#   ./install.sh --user          # install to ~/.claude (non-interactive default)
#   ./install.sh --project DIR   # install to DIR/.claude; the workspace goes OUTSIDE the repo: ~/claude-workspace/<DIR's name>
#   ./install.sh --dry-run       # show what would happen, do nothing
#   ./install.sh --yes           # take every default, ask nothing (CI, scripted installs)
#   --name NAME                  # who the agents work for (shown in their hints)
#   --workspace DIR              # folder the agents work in (journal, agent folders); with --project it may be DIR itself
#   --timezone ZONE              # IANA zone for timestamps, e.g. Europe/Berlin
#   --no-verify                  # skip the checks at the end
#   --verify-all                 # also run every installed test (~5 min) instead of the quick check
#   --enable-cleanup             # also delete trash items older than CCM_TRASH_DAYS and chat-backup copies older than 365 days (off by default)
#   --with-releaser              # (root) release queue: a system user merges into master after gates; cron as root
#   --with-git-guard             # put a git wrapper first in PATH: blocks destructive git in the shared workspace
#   --with-consolidation         # daily memory consolidation + correction stats: each runs a model (your quota)
#   --with-git-snapshot          # daily auto-commit of the workspace (it must be a git repo): every uncommitted change is saved
#   --with-mobile-bot            # Telegram bridge to Claude Code: copy to <dir>/mobile-bot/; the system part (service, secrets file, sudoers) is setup-mobile-bot.sh (root)
#   --with-offsite-backup        # restic backup of your files to S3-compatible storage: copy to <dir>/addons/offsite-backup/, run its setup (own crontab, no root)
#   --with-agent-browser         # a headless browser the agents drive: copy to <dir>/addons/agent-browser/, fetch its engine (no root); service/links = setup-agent-browser.sh (root, optional)
#   --with-net-change            # safe network changes (snapshot, apply, roll back unless confirmed): copy to <dir>/addons/net-change/; setup-net-change.sh needs root
#   --with-dashboard             # local read-only status page of the agents (127.0.0.1:8765): copy to <dir>/addons/dashboard/ (nothing to set up)
#   --with-session-hygiene       # daily: trim old tool outputs from large inactive chat files (only sessions the nightly chat backup holds as they are; text never touched): copy to <dir>/addons/session-hygiene/ + a crontab line
#   --with-reader                # document reader for the workspace (.md/.fb2 in the browser, 127.0.0.1:8001): copy to <dir>/addons/reader/, start it now and after a reboot (crontab, no root)
#   --no-cron                    # do not touch the crontab (also automatic for an install under a temp dir)
#   --prune-cron                 # remove OUR crontab blocks whose install dir no longer exists, then exit
#
# Machine-specific settings go to <install dir>/methodology.conf (kept on re-run).
#
# Re-run safe: existing files are backed up to *.bak-<timestamp>.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DRY_RUN=0
SCOPE=""
PROJECT_DIR=""
YES=0
VERIFY=1
VERIFY_ALL=0
CLEANUP=0
WITH_RELEASER=0
WITH_GIT_GUARD=0
WITH_CONSOLIDATION=0
WITH_GIT_SNAPSHOT=0
WITH_MOBILE_BOT=0
WITH_OFFSITE_BACKUP=0
WITH_AGENT_BROWSER=0
WITH_NET_CHANGE=0
WITH_DASHBOARD=0
WITH_READER=0
WITH_SESSION_HYGIENE=0
NO_CRON=0
PRUNE_CRON=0
OPT_NAME=""
OPT_WORKSPACE=""
OPT_TZ=""

# ---- arg parse -----------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)        SCOPE="user" ;;
    --project)     [[ $# -ge 2 && -n "$2" ]] || { echo "install.sh: --project requires a DIR argument" >&2; exit 2; }
                   SCOPE="project"; PROJECT_DIR="$2"; shift ;;
    --dry-run)     DRY_RUN=1 ;;
    --yes|-y)      YES=1 ;;
    --no-verify)   VERIFY=0 ;;
    --verify-all)  VERIFY_ALL=1 ;;
    --enable-cleanup) CLEANUP=1 ;;
    --with-releaser) WITH_RELEASER=1 ;;
    --with-git-guard) WITH_GIT_GUARD=1 ;;
    --with-consolidation) WITH_CONSOLIDATION=1 ;;
    --with-git-snapshot) WITH_GIT_SNAPSHOT=1 ;;
    --with-mobile-bot) WITH_MOBILE_BOT=1 ;;
    --with-offsite-backup) WITH_OFFSITE_BACKUP=1 ;;
    --with-agent-browser) WITH_AGENT_BROWSER=1 ;;
    --with-net-change) WITH_NET_CHANGE=1 ;;
    --with-dashboard) WITH_DASHBOARD=1 ;;
    --with-reader) WITH_READER=1 ;;
    --with-session-hygiene) WITH_SESSION_HYGIENE=1 ;;
    --no-cron)     NO_CRON=1 ;;
    --prune-cron)  PRUNE_CRON=1 ;;
    --name|--workspace|--timezone)
                   [[ $# -ge 2 ]] || { echo "install.sh: $1 requires a value" >&2; exit 2; }
                   case "$1" in --name) OPT_NAME="$2" ;; --workspace) OPT_WORKSPACE="$2" ;; --timezone) OPT_TZ="$2" ;; esac
                   shift ;;
    -h|--help)     sed -n '2,/^[^#]/{/^#/s/^# \?//p}' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

# ---- helpers -------------------------------------------------------------
say()  { printf '\033[1;36m›\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$*"; }

ask() {
  local prompt="$1" default="${2:-}" ans
  if [[ $YES -eq 1 ]]; then echo "$default"; return; fi
  if [[ -n "$default" ]]; then prompt="$prompt [$default]"; fi
  printf '%s: ' "$prompt" >&2   # stderr: callers capture stdout as the answer — $(ask …)
  read -r ans
  echo "${ans:-$default}"
}

do_or_show() {  # do_or_show <cmd> <arg>... — arguments are passed as-is, never re-parsed by the shell
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  DRY:'; printf ' %q' "$@"; printf '\n'
  else
    "$@"
  fi
}

# ---- which Python -------------------------------------------------------------
# On Windows (Git Bash) `python3` is often the Microsoft Store stub: it prints "Python was not found" and exits 9009.
# The real interpreter there is `python` or the launcher `py -3`. A candidate counts only if it runs and is 3.9 or
# newer. The one chosen runs every python call below and goes into the hook commands of settings.json. When it is not
# python3, <install dir>/lib/pyshim/ gets a `python3` that runs it, and hook-safe.sh puts that folder first in PATH,
# so `python3` inside the hooks and scripts works too. On Linux and macOS python3 is chosen and nothing changes.
ON_WINDOWS=0
case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) ON_WINDOWS=1 ;; esac
[[ -n "${MSYSTEM:-}" ]] && ON_WINDOWS=1
py_works() { "$@" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' </dev/null >/dev/null 2>&1; }
PY=()
for cand in python3 python "py -3"; do
  read -ra words <<<"$cand"
  command -v "${words[0]}" >/dev/null 2>&1 || continue
  if py_works "${words[@]}"; then PY=("${words[@]}"); break; fi
done
if [[ ${#PY[@]} -eq 0 ]]; then
  for cand in python3 python; do
    p=$(command -v "$cand" 2>/dev/null) || continue
    v=$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' </dev/null 2>&1 | tr -d '\r') || true
    if [[ "$p" == *WindowsApps* || "$v" == *"Microsoft Store"* ]]; then warn "$cand ($p) is the Microsoft Store stub, not Python"
    elif [[ "$v" =~ ^[0-9]+\.[0-9]+$ ]]; then warn "$cand is Python $v - 3.9 or newer is needed"; fi
  done
  [[ $ON_WINDOWS -eq 1 ]] && die "Python 3.9+ is required. Windows: winget install Python.Python.3.12 (or python.org, tick \"Add python.exe to PATH\"), then open a new Git Bash and re-run"
  die "python3 (3.9 or newer) is required (hooks and the installer use it)"
fi
py3() { "${PY[@]}" "$@"; }
PY_CMD=$(printf '%q ' "${PY[@]}"); PY_CMD=${PY_CMD% }   # as a shell command line: "python3", "python", "py -3"
[[ "$PY_CMD" == python3 ]] || ok "Python: $PY_CMD ($(py3 -c 'import sys; print(sys.version.split()[0])' | tr -d '\r')) - python3 here is not a working Python"
if [[ $ON_WINDOWS -eq 1 ]]; then
  # Windows Python reads paths natively: /c/Users/... would be C:\c\Users\... to it. C:/Users/... works for both
  # Git Bash and Python, so every path this installer writes (methodology.conf, settings.json) is built from it.
  HOME=$(cygpath -m "$HOME"); export HOME
  REPO_DIR=$(cygpath -m "$REPO_DIR")
  export PYTHONUTF8=1   # print() of "—" or "→" into a pipe: the Windows code page cannot encode it
  # Python on Windows ends printed lines with \r\n; lib/pyshim/sitecustomize.py makes it \n, so $(python ...) gives
  # "x", not "x\r" (the \r would end up inside every path read from methodology.conf)
  export PYTHONPATH="$(cygpath -m "$REPO_DIR/lib/pyshim")${PYTHONPATH:+;$PYTHONPATH}"
fi

# ---- --prune-cron: our marked blocks whose install dir is gone (test installs in /tmp leave them behind) ----
if [[ $PRUNE_CRON -eq 1 ]]; then
  command -v crontab >/dev/null 2>&1 || die "no crontab on this machine"
  cur=$(crontab -l 2>/dev/null)
  new=$(printf '%s\n' "$cur" | py3 -c '
import os, re, sys
out, skip, dropped = [], False, []
for line in sys.stdin.read().split("\n"):
    m = re.match(r"# >>> claude-code-methodology \((.*)\)$", line)
    if m and not os.path.isdir(m.group(1)):
        skip = True; dropped.append(m.group(1)); continue
    if skip:
        if line.startswith("# <<< claude-code-methodology ("): skip = False
        continue
    out.append(line)
sys.stderr.write("".join(f"  removing block of missing {d}\n" for d in dropped) or "  nothing to remove\n")
print("\n".join(out).rstrip("\n"))')
  if [[ $DRY_RUN -eq 1 ]]; then ok "dry run: crontab unchanged"; else printf '%s\n' "$new" | crontab - && ok "crontab pruned"; fi
  exit 0
fi

# ---- system commands the mechanisms call ----------------------------------
# flock, timeout, setsid, crontab are not on a stock macOS; Git Bash on Windows lacks flock, setsid and crontab. Without
# them nothing fails loudly (hooks under hook-safe.sh fail open, jobs are not scheduled), so name each one and what it
# stops, then go on (warn, not die).
DEPS_MISSING=$(py3 "$REPO_DIR/lib/deps_check.py" 2>&1) || DEPS_MISSING="deps_check.py failed: $DEPS_MISSING"
if [[ -n "$DEPS_MISSING" ]]; then
  warn "Some system commands are missing — the install goes on, but these parts will not work until you install them:"
  printf '%s\n' "$DEPS_MISSING" | sed 's/^/  /' >&2
fi

# ---- detect claude-code --------------------------------------------------
say "Detecting Claude Code…"
if command -v claude >/dev/null 2>&1; then
  CLAUDE_VERSION=$(claude --version 2>/dev/null | head -1 || echo unknown)
  ok "claude CLI found: $CLAUDE_VERSION"
else
  warn "claude CLI not found in PATH. Install from https://code.claude.com/docs and re-run."
  if [[ $YES -eq 1 ]]; then yn=y; else read -r -p "Continue anyway? [y/N] " yn || yn=""; fi
  [[ "$yn" =~ ^[Yy]$ ]] || exit 1
fi

# ---- choose scope --------------------------------------------------------
[[ -z "$SCOPE" && $YES -eq 1 ]] && SCOPE="user"
if [[ -z "$SCOPE" ]]; then
  echo
  say "Install scope:"
  echo "  1) user     → ~/.claude/   (active in every project)"
  echo "  2) project  → <dir>/.claude/  (active only in this project)"
  choice=$(ask "Choose 1 or 2" "1")
  case "$choice" in
    1) SCOPE="user" ;;
    2) SCOPE="project" ;;
    *) die "invalid choice" ;;
  esac
fi

if [[ "$SCOPE" == "user" ]]; then
  TARGET="$HOME/.claude"
elif [[ "$SCOPE" == "project" ]]; then
  if [[ -z "$PROJECT_DIR" ]]; then
    PROJECT_DIR=$(ask "Project directory" "$PWD")
  fi
  [[ -d "$PROJECT_DIR" ]] || die "project dir does not exist: $PROJECT_DIR"
  PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd)   # absolute: hooks run with any cwd
  [[ $ON_WINDOWS -eq 1 ]] && PROJECT_DIR=$(cygpath -m "$PROJECT_DIR")   # C:/...: Windows Python reads this path too
  TARGET="$PROJECT_DIR/.claude"
fi

say "Installing to: $TARGET"
do_or_show mkdir -p "$TARGET"/{hooks,scripts,skills,memory,lib,bin,tests}

# ---- settings for this machine (methodology.conf) -------------------------
CONF="$TARGET/methodology.conf"
if [[ -f "$CONF" ]]; then
  ok "keeping your $CONF (delete it to be asked again)"
else
  say "A few settings for this machine (Enter = default):"
  def_name=""   # the full name from the user database; none in Git Bash (no getent) or macOS - then the login name
  command -v getent >/dev/null 2>&1 && def_name=$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f5 | cut -d, -f1) || true
  [[ -n "$def_name" ]] || def_name=${USERNAME:-$(id -un)}
  # --project: the workspace (AGENTS.md, MISTAKES.md, LIBRARY.md, Agents/, the shared documents) must not land in the
  # person's own repo, where it would show in their git status and get committed. Default: ~/claude-workspace/<name of
  # the project folder>; when that folder already serves another project (its .ccm-project names a different path, or
  # it is not ours), <name>-<8 hex of the project path>. --workspace <the project dir> puts it in the repo on purpose.
  if [[ "$SCOPE" == "project" ]]; then
    def_ws="$HOME/claude-workspace/$(basename "$PROJECT_DIR")"
    if [[ -e "$def_ws" && "$(cat "$def_ws/.ccm-project" 2>/dev/null)" != "$PROJECT_DIR" ]]; then
      def_ws="$def_ws-$(py3 -c 'import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:8])' "$PROJECT_DIR")"
    fi
  else def_ws="$HOME/claude-projects"; fi
  def_tz=$(cat /etc/timezone 2>/dev/null || { command -v timedatectl >/dev/null 2>&1 && timedatectl show -p Timezone --value 2>/dev/null; } || true)
  C_NAME="${OPT_NAME:-$(ask "Your name — agents address their hints to it" "$def_name")}"
  C_WS="${OPT_WORKSPACE:-$(ask "Workspace folder (agent folders, mistakes journal)" "$def_ws")}"
  C_TZ="${OPT_TZ:-$(ask "Time zone (IANA, empty = system)" "$def_tz")}"
  # the workspace must be absolute: hooks run with any cwd, a relative "n" would mean a different folder each time
  case "$C_WS" in
    "~") C_WS="$HOME" ;;
    "~/"*) C_WS="$HOME/${C_WS#\~/}" ;;
    /*|[A-Za-z]:[/\\]*) ;;   # C:/... or C:\... = absolute on Windows
    *) warn "workspace \"$C_WS\" is relative — using $HOME/$C_WS"; C_WS="$HOME/$C_WS" ;;
  esac
  [[ $ON_WINDOWS -eq 1 ]] && C_WS=$(cygpath -m "$C_WS")   # /c/x or C:\x -> C:/x: Windows Python reads this path
  C_TRASH="$HOME/.claude-trash"
  C_SECRETS="$HOME/.config/claude-secrets"
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  DRY: would write $CONF (name=$C_NAME, workspace=$C_WS, timezone=$C_TZ)"
  else
    py3 - "$REPO_DIR/methodology.conf.template" "$CONF" "$C_NAME" "$C_WS" "$C_TRASH" "$C_SECRETS" "$C_TZ" <<'PYCONF'
import os, shlex, sys
src, dst, name, ws, trash, secrets, tz = sys.argv[1:]
hb = os.path.join(os.path.expanduser("~"), ".claude", "supervisor", "heartbeat")
text = open(src, encoding="utf-8").read()
for key, val in (("__HUMAN_NAME__", name), ("__WORKSPACE__", ws), ("__TRASH_DIR__", trash),
                 ("__SECRETS_DIR__", secrets), ("__TIMEZONE__", tz), ("__SUPERVISOR_HEARTBEAT__", hb)):
    text = text.replace('"' + key + '"', shlex.quote(val) if val else '""')
open(dst, "w", encoding="utf-8").write(text)
PYCONF
    ok "wrote $CONF"
  fi
  do_or_show mkdir -p "$C_WS" "$C_TRASH" "$C_SECRETS"
  do_or_show chmod 700 "$C_SECRETS"
  # which project this default workspace belongs to: a second project with the same folder name gets its own
  [[ "$SCOPE" == "project" && "$C_WS" == "$def_ws" && $DRY_RUN -eq 0 ]] && echo "$PROJECT_DIR" > "$C_WS/.ccm-project"
fi

# ---- backup existing -----------------------------------------------------
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
backup_if_exists() {  # backup_if_exists <installed path> [repo source] — no backup when it is identical to the source
  local path="$1" src="${2:-}"
  if [[ -e "$path" ]]; then
    [[ -n "$src" ]] && diff -rq "$src" "$path" >/dev/null 2>&1 && return 0
    do_or_show cp -a "$path" "${path}.bak-${TIMESTAMP}"
    warn "backed up existing $path → ${path}.bak-${TIMESTAMP}"
  fi
}

# ---- copy core files -----------------------------------------------------
say "Copying CLAUDE.md (operating core)…"
# CLAUDE.md is meant to be edited (the personal-taste sections). Overwrite it only if it is
# exactly what we installed last time; otherwise keep the user's file and put ours next to it.
STAMP_DIR="$TARGET/.methodology-installed"
sha_of() { py3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }
# CLAUDE.md: never overwrite a file the user wrote or edited. Our rules then go next to it (CLAUDE.md.new) together with
# CLAUDE.md.changes = what changed in OUR rules since the version this user last merged (.methodology-installed/
# CLAUDE.md.base; no base = the whole file). The installing agent merges by meaning: keep the user's notes, add ours,
# ask the user on contradictions, and on an update apply only the changes. Gluing files mechanically (or an @import)
# would load contradicting rules side by side and bring a rejected rule back on every update.
BASE="$STAMP_DIR/CLAUDE.md.base"
claude_md_given() { if [[ $DRY_RUN -eq 0 ]]; then mkdir -p "$STAMP_DIR"; sha_of "$TARGET/CLAUDE.md" > "$STAMP_DIR/CLAUDE.md.sha256"; cp "$REPO_DIR/CLAUDE.md" "$BASE"; fi; }
if [[ ! -e "$TARGET/CLAUDE.md" ]] || \
   [[ -f "$STAMP_DIR/CLAUDE.md.sha256" && "$(sha_of "$TARGET/CLAUDE.md")" == "$(cat "$STAMP_DIR/CLAUDE.md.sha256")" ]]; then
  do_or_show cp "$REPO_DIR/CLAUDE.md" "$TARGET/CLAUDE.md"
  claude_md_given
elif cmp -s "$REPO_DIR/CLAUDE.md" "$TARGET/CLAUDE.md"; then
  [[ -f "$BASE" ]] || claude_md_given   # already current
elif [[ -f "$BASE" ]] && cmp -s "$REPO_DIR/CLAUDE.md" "$BASE"; then
  :   # the user already merged this version of our rules into their own file
else
  do_or_show cp "$REPO_DIR/CLAUDE.md" "$TARGET/CLAUDE.md.new"
  if [[ $DRY_RUN -eq 0 ]]; then
    mkdir -p "$STAMP_DIR"
    if [[ -f "$BASE" ]]; then diff -u --label "our rules, last merged" --label "our rules, now" "$BASE" "$REPO_DIR/CLAUDE.md" > "$TARGET/CLAUDE.md.changes" || true
    else { echo "# First merge: all of our rules are new to this CLAUDE.md"; cat "$REPO_DIR/CLAUDE.md"; } > "$TARGET/CLAUDE.md.changes"; fi
  fi
  warn "CLAUDE.md is your own — not touched. Our rules are in CLAUDE.md.new, what changed in them is CLAUDE.md.changes."
  warn "  Merge (the installing agent does it): keep everything in CLAUDE.md, add from CLAUDE.md.changes what it lacks,"
  warn "  ask the user one line for each rule that contradicts theirs, show the result; then mark it merged:"
  warn "  mv $TARGET/CLAUDE.md.new $BASE   (CLAUDE.md.changes can go to the trash)"
fi

say "Copying hooks…"
for f in "$REPO_DIR"/hooks/*.sh "$REPO_DIR"/hooks/*.py; do
  [[ -f "$f" ]] || continue
  name=$(basename "$f")
  backup_if_exists "$TARGET/hooks/$name" "$f"
  do_or_show cp "$f" "$TARGET/hooks/$name"
  do_or_show chmod +x "$TARGET/hooks/$name"
done

say "Copying scripts…"
for f in "$REPO_DIR"/scripts/*; do
  [[ -f "$f" ]] || continue
  name=$(basename "$f")
  backup_if_exists "$TARGET/scripts/$name" "$f"
  do_or_show cp "$f" "$TARGET/scripts/$name"
  case "$name" in *.sh|*.py) do_or_show chmod +x "$TARGET/scripts/$name" ;;
    *.md|*.txt) ;;
    *) [[ "$(head -c 2 "$f")" == "#!" ]] && do_or_show chmod +x "$TARGET/scripts/$name" ;; esac
done

say "Copying shared library, tools and tests…"
for f in "$REPO_DIR"/lib/*.py "$REPO_DIR"/lib/*.sh; do
  [[ -f "$f" ]] || continue
  do_or_show cp "$f" "$TARGET/lib/$(basename "$f")"
done
# Windows, or python3 is not a working Python: lib/pyshim/ (see "which Python" at the top). env.sh is sourced by
# hook-safe.sh before every hook; python3 there runs the chosen Python; sitecustomize.py (Windows only) gives \n line ends.
SHIM="$TARGET/lib/pyshim"
if [[ $ON_WINDOWS -eq 1 || "$PY_CMD" != python3 ]]; then
  if [[ $DRY_RUN -eq 1 ]]; then echo "  DRY: would write $SHIM/ (python3 -> $PY_CMD, env.sh)"
  else
    mkdir -p "$SHIM"
    shim_u="$SHIM"; [[ $ON_WINDOWS -eq 1 ]] && shim_u=$(cygpath -u "$SHIM")   # a PATH entry: C:/ would split at the colon
    { echo "# Written by install.sh: sourced by hooks/hook-safe.sh before every hook. Re-run install.sh to change it."
      printf 'CCM_PYSHIM=%q\n' "$shim_u"
      echo 'case ":$PATH:" in *":$CCM_PYSHIM:"*) ;; *) PATH="$CCM_PYSHIM:$PATH" ;; esac'
      if [[ $ON_WINDOWS -eq 1 ]]; then
        cp "$REPO_DIR/lib/pyshim/sitecustomize.py" "$SHIM/sitecustomize.py"
        printf 'CCM_PYSHIM_W=%q\n' "$(cygpath -m "$SHIM")"
        echo 'case ";${PYTHONPATH:-};" in *";$CCM_PYSHIM_W;"*) ;; *) PYTHONPATH="$CCM_PYSHIM_W${PYTHONPATH:+;$PYTHONPATH}" ;; esac'
        echo 'PYTHONUTF8=1; export PYTHONPATH PYTHONUTF8'
      fi
      echo 'export PATH CCM_PYSHIM'; } > "$SHIM/env.sh"
    # python3 = the chosen Python, looked up in PATH without this folder (so python3 as the choice is not this file);
    # PATH itself stays as it is, so a bash script the Python starts still finds this python3.
    { echo '#!/usr/bin/env bash'
      echo "# Written by install.sh: python3 on this machine runs $PY_CMD. Re-run install.sh to change it."
      echo '. "$(dirname "$0")/env.sh"'
      echo 'p=":$PATH:"; p=${p//":$CCM_PYSHIM:"/:}'
      echo "real=\$(PATH=\${p:1:\${#p}-2} command -v ${PY[0]}) || { echo \"python3 (lib/pyshim): ${PY[0]} is not in PATH\" >&2; exit 127; }"
      echo "exec \"\$real\"${PY[1]:+ ${PY[*]:1}} \"\$@\""; } > "$SHIM/python3"
    chmod +x "$SHIM/python3"
    . "$SHIM/env.sh"   # from here on, what this installer starts (supervisor, checks, add-on setup) finds it too
    ok "lib/pyshim: python3 in hooks and scripts runs $PY_CMD"
  fi
fi
for f in "$REPO_DIR"/bin/*; do
  [[ -f "$f" ]] || continue
  name=$(basename "$f")
  backup_if_exists "$TARGET/bin/$name" "$f"
  do_or_show cp "$f" "$TARGET/bin/$name"
  do_or_show chmod +x "$TARGET/bin/$name"
done
for f in "$REPO_DIR"/tests/*; do
  [[ -f "$f" ]] || continue
  do_or_show cp "$f" "$TARGET/tests/$(basename "$f")"
  do_or_show chmod +x "$TARGET/tests/$(basename "$f")"
done
if [[ "$SCOPE" == "user" ]] && compgen -G "$TARGET/bin/*" >/dev/null; then
  do_or_show mkdir -p "$HOME/.local/bin"
  BIN_MARK="# claude-code-methodology: runs"
  for f in "$TARGET"/bin/*; do
    l="$HOME/.local/bin/$(basename "$f")"
    [[ -e "$l" && ! -L "$l" ]] && ! grep -qs "^$BIN_MARK" "$l" && { warn "~/.local/bin/$(basename "$f") exists and is not ours — left alone"; continue; }
    do_or_show ln -sfn "$f" "$l"
    # Git Bash without developer mode: ln -s makes a COPY. A copy is never updated and finds no ../lib, so a small script
    # that runs the installed tool goes there instead (marked, so a re-run knows it is ours)
    if [[ $DRY_RUN -eq 0 && ! -L "$l" ]]; then
      { echo '#!/usr/bin/env bash'; echo "$BIN_MARK $f (ln -s copies on this system)"
        [[ -f "$SHIM/env.sh" ]] && printf '. %q\n' "$SHIM/env.sh"
        printf 'exec %q "$@"\n' "$f"; } > "$l" && chmod +x "$l"
    fi
  done
  case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) warn "add ~/.local/bin to PATH for the tools (secret-scan, swap-live, creds, rename-ref)" ;; esac
fi

say "Supervisor registry…"
do_or_show mkdir -p "$TARGET/config"
for f in "$REPO_DIR"/config/*; do
  [[ -f "$f" ]] || continue
  do_or_show cp "$f" "$TARGET/config/$(basename "$f")"
done
if [[ $DRY_RUN -eq 0 && -f "$TARGET/scripts/supervisor.py" ]]; then
  py3 "$TARGET/scripts/supervisor.py" --init "$TARGET/config/supervisor-checks.template.json" 2>&1 | tail -1 || warn "supervisor --init failed"
fi

say "Copying MCP servers…"
do_or_show mkdir -p "$TARGET/mcp"
for f in "$REPO_DIR"/mcp/*.py; do
  [[ -f "$f" ]] || continue
  do_or_show cp "$f" "$TARGET/mcp/$(basename "$f")"
done
# Web search keys (Tavily, Exa): asked once, empty = skip; --yes skips (or takes TAVILY_API_KEY / EXA_API_KEY from
# the environment). Keys go to <secrets>/search.env (0600), never into the workspace. With a key and the claude CLI,
# the server is registered right away — a key without the registration would leave the agent with no search at all.
if [[ -f "$REPO_DIR/mcp/search_mcp.py" && $DRY_RUN -eq 0 ]]; then
  SECRETS=$(py3 "$TARGET/lib/ccm_conf.py" CCM_SECRETS_DIR); SENV="$SECRETS/search.env"
  t_key="${TAVILY_API_KEY:-}"; e_key="${EXA_API_KEY:-}"
  if [[ $YES -eq 0 && ! -s "$SENV" ]]; then
    echo; say "Web search for agents (optional; free tiers exist): paste keys, Enter to skip"
    read -r -s -p "  Tavily API key: " t_key || t_key=""; echo   # no stdin (an agent runs this) = skip, not abort under set -e
    read -r -s -p "  Exa API key: " e_key || e_key=""; echo
  fi
  if [[ -n "$t_key$e_key" ]]; then
    mkdir -p "$SECRETS" && chmod 700 "$SECRETS"
    ( umask 077; : > "$SENV"   # if-blocks, not `[[ ]] && echo`: an empty last key made the subshell fail under set -e
      if [[ -n "$t_key" ]]; then echo "TAVILY_API_KEY=$t_key" >> "$SENV"; fi
      if [[ -n "$e_key" ]]; then echo "EXA_API_KEY=$e_key" >> "$SENV"; fi )
    ok "search keys written to $SENV (mode 600)"
  fi
  if [[ -s "$SENV" ]]; then
    if command -v claude >/dev/null 2>&1; then
      if claude mcp get search >/dev/null 2>&1; then ok "search MCP server already registered"
      elif claude mcp add --scope user search -- "${PY[@]}" "$TARGET/mcp/search_mcp.py" >/dev/null 2>&1; then ok "search MCP server registered (claude mcp add --scope user search)"
      else warn "could not register the search server: claude mcp add --scope user search -- $PY_CMD \"$TARGET/mcp/search_mcp.py\""; fi
    else
      warn "keys saved; register the search server once the claude CLI is installed: claude mcp add --scope user search -- $PY_CMD \"$TARGET/mcp/search_mcp.py\""
    fi
  fi
fi

say "Copying skills…"
for d in "$REPO_DIR"/skills/*/; do
  [[ -d "$d" ]] || continue
  name=$(basename "$d")
  # a backup must NOT stay in skills/: Claude Code loads every folder there, so skills/x.bak-* = a duplicate skill
  if [[ -d "$TARGET/skills/$name" ]] && ! diff -rq "$d" "$TARGET/skills/$name" >/dev/null 2>&1; then
    bk="$TARGET/.methodology-installed/backups/$TIMESTAMP/skills"
    do_or_show mkdir -p "$bk"
    do_or_show cp -a "$TARGET/skills/$name" "$bk/$name"
    warn "backed up your changed skills/$name → $bk/$name"
  fi
  do_or_show mkdir -p "$TARGET/skills/$name"
  do_or_show cp -r "$d." "$TARGET/skills/$name/"   # "$d." — copy the contents; "$d" into an existing dir nests it
done

say "Copying code pitfalls…"
do_or_show mkdir -p "$TARGET/code-pitfalls"
for f in "$REPO_DIR"/code-pitfalls/*.md; do
  [[ -f "$f" ]] || continue
  name=$(basename "$f")
  if [[ -f "$TARGET/code-pitfalls/$name" ]]; then
    warn "code-pitfalls/$name exists — kept yours (lessons are yours to grow)"
  else
    do_or_show cp "$f" "$TARGET/code-pitfalls/$name"
  fi
done

# ---- shared swarm files in the workspace (only what is missing; your files are never overwritten) ----
say "Swarm files in the workspace…"
if [[ $DRY_RUN -eq 1 ]]; then
  echo "  DRY: would copy missing files of swarm-template/ into the workspace and <agents dir>/_example-agent/"
  echo "  DRY: would put CODING-STANDARD.md, PROJECT-WORK.md, DEV-METHODOLOGY.md, PO-INTERFACE.md, WEB-PLAYBOOK.md, DOC-SLOP.md into the workspace (yours kept, ours as .new)"
else
  WS=$(py3 "$TARGET/lib/ccm_conf.py" CCM_WORKSPACE); AG=$(py3 "$TARGET/lib/ccm_conf.py" CCM_AGENTS_DIR)
  added=0
  while IFS= read -r -d '' f; do
    rel=${f#"$REPO_DIR/swarm-template/"}
    [[ "$rel" == README.md ]] && continue
    case "$rel" in Agents/*) dst="$AG/${rel#Agents/}" ;; *) dst="$WS/$rel" ;; esac
    [[ -e "$dst" ]] && continue
    mkdir -p "$(dirname "$dst")" && cp "$f" "$dst" && added=$((added + 1))
  done < <(find "$REPO_DIR/swarm-template" -type f -print0)
  ok "workspace $WS: $added file(s) added from swarm-template (existing ones kept)"
  # the documents every agent follows (CODING-STANDARD, PROJECT-WORK, DEV-METHODOLOGY, PO-INTERFACE, WEB-PLAYBOOK, DOC-SLOP): links rewritten
  # to the workspace; an edited one is kept and the new version goes next to it as .new (+ .changes), like CLAUDE.md
  while IFS= read -r l; do
    case "$l" in "  "*"is yours"*) warn "${l#  }" ;; "  "*) say "${l#  }" ;; *) ok "$l" ;; esac
  done < <(py3 "$REPO_DIR/lib/ws_docs.py" install "$REPO_DIR" "$WS" "$STAMP_DIR" || echo "  ws_docs.py failed - workspace documents not updated")
fi

# Memory = the folder Claude Code's own auto memory loads MEMORY.md from and writes to. Without autoMemoryDirectory in
# settings it uses ~/.claude/projects/<cwd>/memory/, and our memory-template, memory-write-gate and curation would sit on
# a folder Claude never reads. So: a folder the person already set wins; otherwise <install dir>/memory, written into
# settings.json below. Every mechanism finds it through lib/ccm_conf.py (CCM_MEMORY_DIR).
MEMDIR=$(py3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import ccm_conf; print(ccm_conf.memory_dir(sys.argv[2]))' "$REPO_DIR/lib" "$TARGET")
MEM_SET=0; [[ "$MEMDIR" != "$TARGET/memory" ]] && MEM_SET=1
say "Copying memory template into $MEMDIR…"
do_or_show mkdir -p "$MEMDIR"
if [[ ! -f "$MEMDIR/MEMORY.md" ]]; then
  do_or_show cp -r "$REPO_DIR/memory-template/"* "$MEMDIR/"
  ok "memory initialized from template"
else
  warn "$MEMDIR/MEMORY.md already exists — not overwritten. See $REPO_DIR/memory-template/ for reference."
fi
[[ $MEM_SET -eq 1 ]] && ok "memory folder: $MEMDIR (your autoMemoryDirectory, kept)"
# memory Claude's built-in auto memory already wrote elsewhere before this install: shown, never moved
while IFS= read -r d; do
  warn "Claude's built-in memory has files in $d (written before autoMemoryDirectory pointed to $MEMDIR) — move what you want to keep into $MEMDIR and add a line to its MEMORY.md"
done < <(for d in "$HOME"/.claude/projects/*/memory; do
           [[ -d "$d" && "$(cd "$d" && pwd -P)" != "$(cd "$MEMDIR" 2>/dev/null && pwd -P)" ]] && compgen -G "$d/*.md" >/dev/null && echo "$d"
         done | head -5)

# ---- generate settings.json ---------------------------------------------
say "Generating settings.json…"
SETTINGS="$TARGET/settings.json"
backup_if_exists "$SETTINGS"
# Re-running (an update) MERGES into an existing settings.json: the user's permissions, env,
# model and their own hooks stay; only the hook entries that point into $TARGET/hooks/ are replaced.

# Substitute the install target into the template
if [[ $DRY_RUN -eq 0 ]]; then
  # JSON-safe substitution: a path containing " \ | & would break a plain sed replacement
  # --project with the workspace outside the project: Claude Code asks before every edit outside the folder it runs in,
  # so the workspace goes into permissions.additionalDirectories (the agents write their journal and inboxes there)
  EXTRA_DIR=""
  if [[ "$SCOPE" == "project" ]]; then
    EXTRA_DIR=$(py3 "$TARGET/lib/ccm_conf.py" CCM_WORKSPACE)
    case "$EXTRA_DIR/" in "$PROJECT_DIR/"*) EXTRA_DIR="" ;; esac
  fi
  py3 - "$REPO_DIR/settings.template.json" "$SETTINGS" "$TARGET" "$MEMDIR" "$MEM_SET" "$EXTRA_DIR" "$PY_CMD" "$ON_WINDOWS" <<'PYSUB'
import json, re, sys
src, dst, target, memdir, mem_set, extra_dir, py_cmd, on_windows = sys.argv[1:]
# in commands the path sits inside shell double quotes → escape \ " $ ` for the shell first
sh = target.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
text = open(src).read()
text = text.replace("__CLAUDE_DIR_RAW__", json.dumps(target)[1:-1])
text = text.replace("__CLAUDE_DIR__", json.dumps(sh)[1:-1])
ours = json.loads(text)  # fail loudly if the template didn't render to valid JSON
# python3 is not a working Python here (Windows: the Microsoft Store stub): a hook that is a .py file runs through the
# Python install.sh chose - "<dir>/hooks/hook-safe.sh" python "<dir>/hooks/x.py". On Linux and macOS (python3) the
# commands stay as they are and the .py runs by its #! line.
if py_cmd != "python3":
    for groups in ours["hooks"].values():
        for g in groups:
            for h in g.get("hooks", []):
                m = re.match(r'(\s*(?:"[^"]*/hook-safe\.sh"\s+)?)("[^"]*\.py"(?:\s.*)?)$', h.get("command", ""))
                if m:
                    h["command"] = m.group(1) + py_cmd + " " + m.group(2)
if on_windows == "1":   # print() of "—" or "→" into a pipe: the Windows code page cannot encode it
    ours.setdefault("env", {})["PYTHONUTF8"] = "1"
try:
    have = json.load(open(dst))
    if not isinstance(have, dict):
        raise ValueError
except FileNotFoundError:
    have = {}
except ValueError:
    print(f"  ! {dst} is not valid JSON — replaced (the .bak copy has it)", file=sys.stderr)
    have = {}
mine = (target.rstrip("/") + "/hooks/", sh.rstrip("/") + "/hooks/")
merged = dict(have)
for k, v in ours.items():
    if k == "hooks":
        continue
    if k == "env" and isinstance(have.get("env"), dict):
        merged["env"] = {**have["env"], **v}      # our variables are refreshed, theirs stay
    else:
        merged.setdefault(k, v)                   # anything the user set wins
if mem_set != "1":   # the person's own autoMemoryDirectory (here or in settings.local.json) is never touched
    merged.setdefault("autoMemoryDirectory", memdir)
if extra_dir:        # added once; the person's own entries stay
    perms = merged.get("permissions") if isinstance(merged.get("permissions"), dict) else {}
    dirs = perms.get("additionalDirectories") if isinstance(perms.get("additionalDirectories"), list) else []
    if extra_dir not in dirs:
        dirs = dirs + [extra_dir]
    merged["permissions"] = {**perms, "additionalDirectories": dirs}
hooks = {}
for event, groups in (have.get("hooks") or {}).items():
    for g in groups:
        keep = [h for h in g.get("hooks", []) if not any(m in h.get("command", "") for m in mine)]
        if keep:
            hooks.setdefault(event, []).append({**g, "hooks": keep})
for event, groups in ours["hooks"].items():
    hooks.setdefault(event, []).extend(groups)
merged["hooks"] = hooks
tmp = dst + ".tmp"
with open(tmp, "w") as f:
    json.dump(merged, f, indent=2)
    f.write("\n")
json.load(open(tmp))
import os
os.replace(tmp, dst)
PYSUB
  ok "wrote $SETTINGS"
else
  echo "  DRY: would write $SETTINGS with __CLAUDE_DIR__=$TARGET"
fi

# ---- python deps (optional) ---------------------------------------------
echo
say "Optional Python dependencies (for document extraction, mobile-bot, etc.)"
echo "  - poppler-utils (PDF extraction)  — system package"
echo "  - lynx, pandoc (HTML → text/md)   — system package"
echo "  - faster-whisper (voice)          — pip"
echo "  - ffmpeg, yt-dlp (video)          — system + pip"
yn=$(ask "Try to install system deps via apt now? (y/N)" "N")
if [[ "$yn" =~ ^[Yy]$ ]]; then
  if command -v apt-get >/dev/null 2>&1; then
    do_or_show sudo apt-get update -qq
    do_or_show sudo apt-get install -y poppler-utils lynx pandoc ffmpeg
  else
    warn "apt-get not available — install manually for your OS"
  fi
fi

# ---- scheduled jobs (cron) ---------------------------------------------------
# One marked block in the user's crontab, replaced on every run (no duplicates; other lines untouched).
CRON_BEGIN="# >>> claude-code-methodology ($TARGET)"
CRON_END="# <<< claude-code-methodology ($TARGET)"
q() { printf '%q' "$1"; }
# quota every minute, one run at a time: flock where there is one (none on macOS/Windows: the run is short, timeout 50 caps it)
QLOCK=""; command -v flock >/dev/null 2>&1 && QLOCK="flock -n $(q "$HOME/.claude/quota.lock")"
# Nothing that DELETES is scheduled unless asked: trash cleanup needs --enable-cleanup or a "y" here.
if [[ $CLEANUP -eq 0 && $YES -eq 0 ]]; then
  yn=$(ask "Delete trash items (older than CCM_TRASH_DAYS) and chat-backup copies (older than 365 days) automatically, daily? (y/N)" "N")
  [[ "$yn" =~ ^[Yy]$ ]] && CLEANUP=1
fi
CRON_LINES="$CRON_BEGIN
*/10 * * * * $PY_CMD $(q "$TARGET/hooks/trash-guard.py") --measure >/dev/null 2>&1
55 * * * * $PY_CMD $(q "$TARGET/hooks/abbr-guard.py") --build-vocab >/dev/null 2>&1
* * * * * $PY_CMD $(q "$TARGET/scripts/remind.py") --fire >/dev/null 2>&1
*/15 * * * * $PY_CMD $(q "$TARGET/scripts/blockers.py") run >/dev/null 2>&1
*/15 * * * * $PY_CMD $(q "$TARGET/scripts/supervisor.py") >/dev/null 2>&1
* * * * * $QLOCK timeout 50 $PY_CMD $(q "$TARGET/scripts/quota_status.py") --json --out $(q "$HOME/.claude/quota-status.json") 2>>$(q "$HOME/.claude/quota.err")
7 * * * * $PY_CMD $(q "$TARGET/scripts/quota_log_line.py") >/dev/null 2>&1
15 * * * * $PY_CMD $(q "$TARGET/scripts/token_daily_report.py") --after 8 >/dev/null 2>&1
*/10 * * * * $(q "$TARGET/scripts/mech_snapshot.sh") >/dev/null 2>&1
35 * * * * $PY_CMD $(q "$TARGET/scripts/stats_collect.py") >/dev/null 2>&1
40 * * * * $PY_CMD $(q "$TARGET/scripts/stats_adoption.py") >/dev/null 2>&1
45 * * * * $PY_CMD $(q "$TARGET/scripts/stats_orphan_docs.py") >/dev/null 2>&1
*/15 * * * * $PY_CMD $(q "$TARGET/scripts/stats_projects.py") >/dev/null 2>&1
35 12 * * 0 mkdir -p $(q "$HOME/.claude/logs") && $(q "$TARGET/scripts/mistakes_review.sh") >> $(q "$HOME/.claude/logs/mistakes-review.log") 2>&1
@reboot sleep 300 && $(q "$TARGET/scripts/mistakes_review_catchup.sh") >/dev/null 2>&1
52 12 * * * $PY_CMD $(q "$TARGET/scripts/library_check.py") >/dev/null 2>&1
50 12 * * * $(q "$TARGET/scripts/swarm_tools_check.sh") >/dev/null 2>&1
@reboot sleep 120 && $(q "$TARGET/scripts/git_empty_objects_check.sh") >/dev/null 2>&1
25 5 * * * $(q "$TARGET/scripts/public_gate_selftest.sh") >/dev/null 2>&1
30 12 * * 0 $(q "$TARGET/scripts/prune_watchman_state.sh") >/dev/null 2>&1
10 3 * * * mkdir -p $(q "$HOME/.claude/logs") && RETENTION_DAYS=$([[ $CLEANUP -eq 1 ]] && echo 365 || echo 0) $(q "$TARGET/scripts/backup-chats.sh") >> $(q "$HOME/.claude/logs/chat-backup.log") 2>&1"
# the chat backup is a COPY (rsync with hard links): it deletes nothing unless cleanup is on, then day-folders > 365 days
[[ $WITH_CONSOLIDATION -eq 1 ]] && CRON_LINES="$CRON_LINES
20 * * * * $(q "$TARGET/scripts/memory_consolidation.sh") >/dev/null 2>&1
20 * * * * $PY_CMD $(q "$TARGET/scripts/stats_corrections.py") --days 3 --after 6 >/dev/null 2>&1"
if [[ $WITH_GIT_SNAPSHOT -eq 1 ]]; then
  WS_SNAP=$(py3 "$TARGET/lib/ccm_conf.py" CCM_WORKSPACE)
  git -C "$WS_SNAP" rev-parse --git-dir >/dev/null 2>&1 || warn "--with-git-snapshot: $WS_SNAP is not a git repo yet — the snapshot will log FAIL until you run git init there"
  CRON_LINES="$CRON_LINES
0 4 * * * mkdir -p $(q "$HOME/.claude/logs") && LOG=$(q "$HOME/.claude/logs/git-snapshot.log") $(q "$TARGET/scripts/daily-git-snapshot.sh") $(q "$WS_SNAP") >/dev/null 2>&1"
fi
# the reader add-on is started after a reboot from here (no root, no service manager needed); install.sh starts it now too
[[ $WITH_READER -eq 1 ]] && CRON_LINES="$CRON_LINES
@reboot sleep 30 && mkdir -p $(q "$HOME/.claude/logs") && $PY_CMD $(q "$TARGET/addons/reader/reader-server.py") >> $(q "$HOME/.claude/logs/reader.log") 2>&1"
# session hygiene rewrites chat files: only from 04:00 (after the 03:10 chat backup), retried hourly by catchup-run while
# that backup is not fresh (rc 75); it touches only sessions the backup holds exactly as they are now
[[ $WITH_SESSION_HYGIENE -eq 1 ]] && CRON_LINES="$CRON_LINES
7 * * * * $(q "$TARGET/bin/catchup-run") session_hygiene daily --after 4 -- $PY_CMD $(q "$TARGET/addons/session-hygiene/session-hygiene.py")"
[[ $CLEANUP -eq 1 ]] && CRON_LINES="$CRON_LINES
35 4 * * * $PY_CMD $(q "$TARGET/hooks/trash-guard.py") --clean >/dev/null 2>&1"
CRON_LINES="$CRON_LINES
$CRON_END"
echo
if [[ $CLEANUP -eq 1 ]]; then say "Scheduled jobs: supervisor, quota, reports, stats, journal checks, reminders, blockers, trash size, chat backup + cleanup (on: trash, chat copies > 365 days)"
else say "Scheduled jobs: supervisor, quota, reports, stats, journal checks, reminders, blockers, trash size, chat backup — a copy, nothing deleted (cleanup off: --enable-cleanup; model-run jobs off: --with-consolidation; workspace auto-commit off: --with-git-snapshot)"; fi
case "$TARGET" in
  /tmp/*|/var/tmp/*|"${TMPDIR:-/nonexistent}"/*) [[ $NO_CRON -eq 1 ]] || warn "install dir is under a temp dir — crontab left alone (a test install must not schedule jobs)"; NO_CRON=1 ;;
esac
if [[ $NO_CRON -eq 1 ]]; then
  say "crontab not touched (--no-cron or a temp install dir)"
elif [[ $DRY_RUN -eq 1 ]]; then
  printf '  DRY: would put into crontab:\n%s\n' "$CRON_LINES"
elif command -v crontab >/dev/null 2>&1; then
  { crontab -l 2>/dev/null | awk -v b="$CRON_BEGIN" -v e="$CRON_END" '$0==b{skip=1;next} $0==e{skip=0;next} !skip'
    printf '%s\n' "$CRON_LINES"; } | crontab - && ok "crontab updated ($(crontab -l | grep -cF "$TARGET") lines)"
else
  warn "no crontab on this machine — these scheduled jobs will not run until you add them to your scheduler by hand:"
  printf '%s\n' "$CRON_LINES" >&2
  if [[ $ON_WINDOWS -eq 1 ]]; then
    # Task Scheduler runs a job through Git Bash's bash.exe; the most needed one is the reminders (every minute)
    warn "Windows: Task Scheduler takes the same commands through Git Bash. The reminders, every minute (in cmd or PowerShell):"
    warn "  schtasks /Create /SC MINUTE /MO 1 /TN ccm-remind /TR \"\\\"$(cygpath -w "$(command -v bash)")\\\" -lc '. $(q "$SHIM/env.sh"); python3 $(q "$TARGET/scripts/remind.py") --fire'\""
    warn "  the rest the same way (. env.sh first: the jobs call python3), /SC MINUTE /MO 10 for */10, /SC HOURLY for an hourly line, /SC DAILY /ST 03:10 for a daily one (README.md, Platforms)"
  fi
fi

# ---- add-ons (each only with its own flag) -----------------------------------
# An add-on is copied to <dir>/addons/<name>/ (mobile-bot: <dir>/mobile-bot/). Its non-root setup runs here; setup that needs
# root runs only when this installer is root already - otherwise the exact sudo line is printed (we never call sudo here).
# Its supervisor entries are merged into the registry by name: missing ones are added, existing ones are never touched.
REGISTRY="$(py3 "$TARGET/lib/ccm_conf.py" CCM_SUPERVISOR_DIR 2>/dev/null || echo "$HOME/.claude/supervisor")/checks.json"
SETUP_DRY=(); [[ $DRY_RUN -eq 1 ]] && SETUP_DRY=(--dry-run)
ADDONS_DONE=()
SEC=$(py3 "$TARGET/lib/ccm_conf.py" CCM_SECRETS_DIR 2>/dev/null || echo "$HOME/.config/claude-secrets")
# Scripts to run: the installed copies - on a dry run nothing is copied, so the repo's own copies stand in.
if [[ $DRY_RUN -eq 1 ]]; then MB_DIR="$REPO_DIR/addons/mobile-bot"; AD_DIR="$REPO_DIR/addons"
else MB_DIR="$TARGET/mobile-bot"; AD_DIR="$TARGET/addons"; fi

copy_addon() {  # copy_addon <name> <dest dir>
  do_or_show mkdir -p "$2"
  do_or_show cp -r "$REPO_DIR/addons/$1/." "$2/"   # "/." copies dotfiles too (.env.template)
  ADDONS_DONE+=("$1")
}
merge_checks() {  # merge_checks <name> — supervisor-checks.json of the add-on into the registry, by "name"; existing entries stay
  local src="$REPO_DIR/addons/$1/supervisor-checks.json"
  [[ -f "$src" ]] || return 0
  if [[ $DRY_RUN -eq 1 ]]; then echo "  DRY: would merge the supervisor checks of $1 into $REGISTRY"; return 0; fi
  py3 - "$src" "$REGISTRY" "$1" <<'PYMERGE' || warn "could not merge the supervisor checks of $1 into $REGISTRY"
import json, os, sys
src, dst, name = sys.argv[1:]
new = json.load(open(src, encoding="utf-8")).get("checks", [])
try:
    reg = json.load(open(dst, encoding="utf-8"))
except FileNotFoundError:
    reg = {"checks": []}
have = {c.get("name") for c in reg.get("checks", [])}
added = [c for c in new if c.get("name") not in have]
reg.setdefault("checks", []).extend(added)
if added:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2, ensure_ascii=False); f.write("\n")
    os.replace(tmp, dst)
print(f"  supervisor: {name}: {len(added)} check(s) added, {len(new) - len(added)} already there")
PYMERGE
}
root_setup() {  # root_setup <script> <args...> — run as root, or print the exact sudo command
  if [[ $DRY_RUN -eq 1 ]]; then bash "$@" --dry-run || warn "dry run of $(basename "$1") failed — see above"
  elif [[ $(id -u) -eq 0 ]]; then bash "$@" || warn "$(basename "$1") failed — see above"
  else warn "needs root, run: sudo bash $(printf '%q ' "$@")"; fi
}

# The old y/N question is the same thing as --with-mobile-bot; asked only when nothing says otherwise.
if [[ $WITH_MOBILE_BOT -eq 0 && $YES -eq 0 ]]; then
  echo
  say "Optional add-on: mobile-bot (Telegram bridge to Claude Code)"
  yn=$(ask "Install mobile-bot? (y/N)" "N")
  [[ "$yn" =~ ^[Yy]$ ]] && WITH_MOBILE_BOT=1
fi

if [[ $WITH_MOBILE_BOT -eq 1 ]]; then
  echo; say "add-on mobile-bot…"
  copy_addon mobile-bot "$TARGET/mobile-bot"
  merge_checks mobile-bot
  ok "mobile-bot copied to $TARGET/mobile-bot"
  warn "mobile-bot is not running yet. 1) put the bot token and your Telegram id into $SEC/mobile-bot.env (template: $TARGET/mobile-bot/.env.template, every key explained)"
  root_setup "$MB_DIR/setup-mobile-bot.sh"
  warn "2) then see $TARGET/mobile-bot/README.md (/setpin, optional --with-swarm for letters to agents)"
fi
if [[ $WITH_OFFSITE_BACKUP -eq 1 ]]; then
  echo; say "add-on offsite-backup…"
  copy_addon offsite-backup "$TARGET/addons/offsite-backup"
  OB=(bash "$AD_DIR/offsite-backup/setup-offsite-backup.sh" ${SETUP_DRY[@]+"${SETUP_DRY[@]}"} --dest "$TARGET/scripts/backup")
  [[ $NO_CRON -eq 1 ]] && OB+=(--no-cron)
  "${OB[@]}" || warn "offsite-backup setup stopped (rc $?) — restic missing? See above; re-run the same line after fixing"
  merge_checks offsite-backup
  warn "offsite-backup needs your storage keys: copy restic.env.template (in $SEC) to restic.env and fill it — see $TARGET/addons/offsite-backup/README.md"
fi
if [[ $WITH_AGENT_BROWSER -eq 1 ]]; then
  echo; say "add-on agent-browser…"
  copy_addon agent-browser "$TARGET/addons/agent-browser"
  bash "$AD_DIR/agent-browser/install-engine.sh" ${SETUP_DRY[@]+"${SETUP_DRY[@]}"} || warn "browser engine not installed (needs node + npm) — re-run: bash $TARGET/addons/agent-browser/install-engine.sh"
  merge_checks agent-browser
  warn "optional, root: sudo bash $TARGET/addons/agent-browser/setup-agent-browser.sh --link --browser-service   (links br into /usr/local/bin, runs a headless Chrome as a service; skip if you already run Chrome with remote debugging and set CCM_BR_CDP)"
fi
if [[ $WITH_NET_CHANGE -eq 1 ]]; then
  echo; say "add-on net-change…"
  copy_addon net-change "$TARGET/addons/net-change"
  root_setup "$AD_DIR/net-change/setup-net-change.sh"
  merge_checks net-change
fi
if [[ $WITH_DASHBOARD -eq 1 ]]; then
  echo; say "add-on dashboard…"
  copy_addon dashboard "$TARGET/addons/dashboard"
  ok "dashboard copied — start it: $PY_CMD $TARGET/addons/dashboard/dashboard.py (read-only, 127.0.0.1:8765)"
fi
if [[ $WITH_READER -eq 1 ]]; then
  echo; say "add-on reader…"
  copy_addon reader "$TARGET/addons/reader"
  merge_checks reader
  RD=("${PY[@]}" "$AD_DIR/reader/reader-server.py")
  if [[ $DRY_RUN -eq 1 ]]; then echo "  DRY: would start: ${RD[*]} >> $HOME/.claude/logs/reader.log 2>&1 &"
  elif [[ $NO_CRON -eq 1 ]]; then warn "reader not started (--no-cron or a temp install dir: nothing runs in the background). Start it: ${RD[*]} &"
  elif py3 "$AD_DIR/reader/reader-check.py" >/dev/null 2>&1; then ok "reader already answers — left as it is"
  else
    mkdir -p "$HOME/.claude/logs"
    if command -v setsid >/dev/null 2>&1; then nohup setsid "${RD[@]}" >> "$HOME/.claude/logs/reader.log" 2>&1 < /dev/null &
    else nohup "${RD[@]}" >> "$HOME/.claude/logs/reader.log" 2>&1 < /dev/null & disown; fi   # no setsid (macOS, Git Bash): it outlives this installer all the same
    if py3 "$AD_DIR/reader/reader-check.py" --wait 5 >/dev/null; then
      ok "reader started: $(py3 "$AD_DIR/reader/reader-check.py" | sed 's/^reader answers: //; s#/api/last$#/#')  (after a reboot: the crontab line)"
    else warn "reader did not start — see $HOME/.claude/logs/reader.log (port taken? set CCM_READER_PORT in methodology.conf)"; fi
  fi
  say "  reader: this machine only by default. CCM_READER_BIND=0.0.0.0 opens it to the network with NO password — use a proxy that asks for one"
  say "  reader: a folder for documents agents leave for you to read = CCM_READER_SHARED in methodology.conf (empty = no such section)"
fi
if [[ $WITH_SESSION_HYGIENE -eq 1 ]]; then
  echo; say "add-on session-hygiene…"
  copy_addon session-hygiene "$TARGET/addons/session-hygiene"
  merge_checks session-hygiene
  if [[ $NO_CRON -eq 1 ]]; then warn "session-hygiene: not scheduled (--no-cron or a temp install dir). By hand: $PY_CMD $TARGET/addons/session-hygiene/session-hygiene.py --dry-run"
  else ok "session-hygiene: daily from 04:00 (crontab), log ~/.claude/cron-logs/session_hygiene.log; it waits for the nightly chat backup and never touches a session the backup does not hold as it is"; fi
fi

# ---- optional system parts (explicit flags only) -----------------------------
if [[ $WITH_GIT_GUARD -eq 1 ]]; then
  say "git guard (wrapper first in PATH)…"
  if [[ $DRY_RUN -eq 1 ]]; then bash "$TARGET/scripts/setup-git-guard.sh" --dry-run || true
  else bash "$TARGET/scripts/setup-git-guard.sh" --rc-file "$HOME/.bashrc" || warn "git guard setup failed — see above"; fi
fi
if [[ $WITH_RELEASER -eq 1 ]]; then
  say "release queue (system user, state dir, root cron)…"
  if [[ $DRY_RUN -eq 1 ]]; then bash "$TARGET/scripts/setup-releaser.sh" --dry-run --cron || true
  elif [[ $(id -u) -eq 0 ]]; then bash "$TARGET/scripts/setup-releaser.sh" --cron || warn "releaser setup failed — see above"
  else sudo bash "$TARGET/scripts/setup-releaser.sh" --owner "$(id -un)" --cron || warn "releaser setup needs root: sudo bash $TARGET/scripts/setup-releaser.sh --owner $(id -un) --cron"; fi
fi

# ---- verify: run the installed tests against the installed copies -----------
# Quick by default (seconds): check-install item by item + one supervisor run, PASS = 0 problems + 0 broken.
# --verify-all: every installed test (~5 min; each runs in its own temp sandbox).
TESTS_FAILED=0
if [[ $VERIFY -eq 1 && $DRY_RUN -eq 0 ]]; then
  if [[ "$SCOPE" == "user" ]]; then CHECK=(--user); else CHECK=(--project "$PROJECT_DIR"); fi
  echo
  say "Checking the installation item by item…"
  if out=$(py3 "$REPO_DIR/check-install.py" "${CHECK[@]}" 2>&1); then ok "$(printf '%s\n' "$out" | grep -E 'ok, .* missing' | tail -1)"
    printf '%s\n' "$out" | sed -n '/^Accounts still/,/^$/p'   # only what is missing, each line -> docs/accounts.md
  else TESTS_FAILED=$((TESTS_FAILED + 1)); printf '%s\n' "$out" | grep -E '^MISS|missing or broken' | head -12 >&2; fi
  if [[ -f "$TARGET/scripts/supervisor.py" ]]; then
    say "One supervisor run on the fresh install…"
    py3 "$TARGET/scripts/supervisor.py" >/dev/null 2>&1
    sv=$(py3 -c 'import json,os,sys
p=os.path.join(os.path.expanduser("~"),".claude","supervisor","summary.json")
try: d=json.load(open(p))
except Exception as e: print("no summary:", type(e).__name__); sys.exit(1)
pr,br=d.get("problems",[]),d.get("broken_checks",[])
print(f"supervisor: {len(pr)} problems, {len(br)} broken" + ("" if not pr+br else " - " + "; ".join(pr+br)))
sys.exit(1 if pr or br else 0)' 2>&1) && ok "$sv" || { TESTS_FAILED=$((TESTS_FAILED + 1)); warn "$sv"; }
  fi
fi
if [[ $VERIFY -eq 1 && $VERIFY_ALL -eq 1 && $DRY_RUN -eq 0 ]] && compgen -G "$TARGET/tests/*-test.*" >/dev/null; then
  echo
  say "Checking the installed mechanisms (each test runs in a temp sandbox)…"
  for t in "$TARGET"/tests/*-test.*; do
    case "$t" in *.py) runner=py3 ;; *.sh) runner=bash ;; *) continue ;; esac
    if out=$(CCM_REPO_DIR="$REPO_DIR" "$runner" "$t" 2>&1); then   # a test that needs the repo's docs/ finds the clone here
      ok "$(printf '%s\n' "$out" | tail -1)"
    else
      TESTS_FAILED=$((TESTS_FAILED + 1))
      warn "$(basename "$t") FAILED:"; printf '%s\n' "$out" | tail -8 >&2
    fi
  done
fi

if [[ $VERIFY -eq 1 && $VERIFY_ALL -eq 1 && $DRY_RUN -eq 0 ]]; then
  # add-on tests: addons/<name>/tests/*-test.*  and  mobile-bot/tests/test_*.py (each runs from its own folder, in a temp sandbox)
  ADDON_TESTS=()
  for t in "$TARGET"/addons/*/tests/*-test.* "$TARGET"/mobile-bot/tests/test_*.py; do [[ -f "$t" ]] && ADDON_TESTS+=("$t"); done
  if [[ ${#ADDON_TESTS[@]} -gt 0 ]]; then
    echo
    say "Checking the installed add-ons…"
    for t in "${ADDON_TESTS[@]}"; do
      case "$t" in *.py) runner=py3 ;; *.sh) runner=bash ;; *) continue ;; esac
      if out=$(cd "$(dirname "$t")/.." && "$runner" "$t" 2>&1); then
        ok "$(basename "$(dirname "$(dirname "$t")")"): $(printf '%s\n' "$out" | tail -1)"
      else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        warn "$t FAILED:"; printf '%s\n' "$out" | tail -8 >&2
      fi
    done
  fi
fi

# what was installed, from where: /update reads it to say what is new and to install the same way again
if [[ $DRY_RUN -eq 0 ]]; then
  mkdir -p "$STAMP_DIR"
  { echo "repo=$REPO_DIR"; echo "commit=$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "scope=$SCOPE"; [[ "$SCOPE" == "project" ]] && echo "project=$PROJECT_DIR"; echo "date=$(date -u +%Y-%m-%dT%H:%MZ)"; } > "$STAMP_DIR/source"
fi

# ---- done ---------------------------------------------------------------
echo
if [[ $TESTS_FAILED -gt 0 ]]; then
  warn "Installed, but $TESTS_FAILED check(s) failed — see above. The failing mechanism may not work on this machine."
else
  ok "Install complete."
fi
[[ -z "$DEPS_MISSING" ]] || warn "Missing system commands: $(printf '%s\n' "$DEPS_MISSING" | sed -n 's/^missing: \([^ ]*\) .*/\1/p' | paste -sd' ' -) — see \"missing:\" at the top"
[[ $VERIFY_ALL -eq 1 ]] || echo "  (quick check done; every mechanism's own test: ./install.sh --verify-all … — about 5 min)"
if [[ $DRY_RUN -eq 0 ]]; then
  WS_END=$(py3 "$TARGET/lib/ccm_conf.py" CCM_WORKSPACE)
  echo; say "Workspace (agent folders, mistakes journal, shared documents): $WS_END"
  if [[ "$SCOPE" == "project" ]]; then
    case "$WS_END/" in "$PROJECT_DIR/"*) echo "  (inside your project: these files show up in its git status)" ;;
      *) echo "  (outside $PROJECT_DIR, so none of it shows up in your project's git)" ;; esac
  fi
fi
echo
echo "Next steps:"
echo "  1) Start a new Claude Code session (existing sessions won't pick up the new config)"
echo "  2) Later, to update: tell your agent \"update the system\" (/update)"
echo "  3) Read $REPO_DIR/docs/getting-started.md (first day) and docs/accounts.md (optional accounts: search, backup, phone bot)"
echo
echo "To undo: in $TARGET, restore the *.bak-${TIMESTAMP} copies over the files they back up, and remove"
echo "what this repo added (hooks/, scripts/, skills/, code-pitfalls/, lib/, bin/, mcp/, tests/, methodology.conf, addons/, mobile-bot/,"
echo "(add-ons: each has setup-<name>.sh --uninstall; with --with-git-guard: scripts/setup-git-guard.sh --uninstall; with --with-releaser: /etc/cron.d/ccm-releaser and the releaser user)"
echo ".methodology-installed/), the ~/.local/bin links to bin/ and the marked block in crontab -l."
echo "Do NOT delete $TARGET as a whole: it also holds your own Claude Code settings, memory and history."
[[ $TESTS_FAILED -eq 0 ]] || exit 3
