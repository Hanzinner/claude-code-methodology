#!/usr/bin/env bash
# Bootstrap installer for claude-code-methodology.
#
# Detects Claude Code, asks where to install (user vs project scope),
# copies hooks/scripts/skills with path-rewriting, generates settings.json,
# offers optional Python deps, offers optional addons (mobile-bot).
#
# Usage:
#   ./install.sh                 # interactive
#   ./install.sh --user          # install to ~/.claude (non-interactive default)
#   ./install.sh --project DIR   # install to DIR/.claude
#   ./install.sh --dry-run       # show what would happen, do nothing
#   ./install.sh --yes           # take every default, ask nothing (CI, scripted installs)
#   --name NAME                  # who the agents work for (shown in their hints)
#   --workspace DIR              # folder the agents work in (journal, agent folders)
#   --timezone ZONE              # IANA zone for timestamps, e.g. Europe/Berlin
#   --no-verify                  # skip running the installed tests at the end
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

# ---- detect claude-code --------------------------------------------------
say "Detecting Claude Code…"
if command -v claude >/dev/null 2>&1; then
  CLAUDE_VERSION=$(claude --version 2>/dev/null | head -1 || echo unknown)
  ok "claude CLI found: $CLAUDE_VERSION"
else
  warn "claude CLI not found in PATH. Install from https://code.claude.com/docs and re-run."
  if [[ $YES -eq 1 ]]; then yn=y; else read -r -p "Continue anyway? [y/N] " yn; fi
  [[ "$yn" =~ ^[Yy]$ ]] || exit 1
fi

# ---- choose scope --------------------------------------------------------
command -v python3 >/dev/null 2>&1 || die "python3 is required (hooks and the installer use it)"
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
  def_name=$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f5 | cut -d, -f1)
  [[ -n "$def_name" ]] || def_name=$(id -un)
  if [[ "$SCOPE" == "project" ]]; then def_ws="$PROJECT_DIR"; else def_ws="$HOME/claude-projects"; fi
  def_tz=$(cat /etc/timezone 2>/dev/null || timedatectl show -p Timezone --value 2>/dev/null || true)
  C_NAME="${OPT_NAME:-$(ask "Your name — agents address their hints to it" "$def_name")}"
  C_WS="${OPT_WORKSPACE:-$(ask "Workspace folder (agent folders, mistakes journal)" "$def_ws")}"
  C_TZ="${OPT_TZ:-$(ask "Time zone (IANA, empty = system)" "$def_tz")}"
  C_TRASH="$HOME/.Trash"
  C_SECRETS="$HOME/.config/claude-secrets"
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  DRY: would write $CONF (name=$C_NAME, workspace=$C_WS, timezone=$C_TZ)"
  else
    python3 - "$REPO_DIR/methodology.conf.template" "$CONF" "$C_NAME" "$C_WS" "$C_TRASH" "$C_SECRETS" "$C_TZ" <<'PYCONF'
import shlex, sys
src, dst, name, ws, trash, secrets, tz = sys.argv[1:]
text = open(src, encoding="utf-8").read()
for key, val in (("__HUMAN_NAME__", name), ("__WORKSPACE__", ws), ("__TRASH_DIR__", trash),
                 ("__SECRETS_DIR__", secrets), ("__TIMEZONE__", tz)):
    text = text.replace('"' + key + '"', shlex.quote(val) if val else '""')
open(dst, "w", encoding="utf-8").write(text)
PYCONF
    ok "wrote $CONF"
  fi
  do_or_show mkdir -p "$C_WS" "$C_TRASH" "$C_SECRETS"
  do_or_show chmod 700 "$C_SECRETS"
fi

# ---- backup existing -----------------------------------------------------
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
backup_if_exists() {
  local path="$1"
  if [[ -e "$path" ]]; then
    do_or_show cp -a "$path" "${path}.bak-${TIMESTAMP}"
    warn "backed up existing $path → ${path}.bak-${TIMESTAMP}"
  fi
}

# ---- copy core files -----------------------------------------------------
say "Copying CLAUDE.md (operating core)…"
# CLAUDE.md is meant to be edited (the personal-taste sections). Overwrite it only if it is
# exactly what we installed last time; otherwise keep the user's file and put ours next to it.
STAMP_DIR="$TARGET/.methodology-installed"
sha_of() { python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }
if [[ ! -e "$TARGET/CLAUDE.md" ]] || \
   [[ -f "$STAMP_DIR/CLAUDE.md.sha256" && "$(sha_of "$TARGET/CLAUDE.md")" == "$(cat "$STAMP_DIR/CLAUDE.md.sha256")" ]]; then
  do_or_show cp "$REPO_DIR/CLAUDE.md" "$TARGET/CLAUDE.md"
  if [[ $DRY_RUN -eq 0 ]]; then mkdir -p "$STAMP_DIR"; sha_of "$TARGET/CLAUDE.md" > "$STAMP_DIR/CLAUDE.md.sha256"; fi
elif cmp -s "$REPO_DIR/CLAUDE.md" "$TARGET/CLAUDE.md"; then
  :   # already current
else
  do_or_show cp "$REPO_DIR/CLAUDE.md" "$TARGET/CLAUDE.md.new"
  warn "CLAUDE.md has your own edits — kept. The new version is CLAUDE.md.new; merge what you want."
fi

say "Copying hooks…"
for f in "$REPO_DIR"/hooks/*.sh "$REPO_DIR"/hooks/*.py; do
  [[ -f "$f" ]] || continue
  name=$(basename "$f")
  backup_if_exists "$TARGET/hooks/$name"
  do_or_show cp "$f" "$TARGET/hooks/$name"
  do_or_show chmod +x "$TARGET/hooks/$name"
done

say "Copying scripts…"
for f in "$REPO_DIR"/scripts/*; do
  [[ -f "$f" ]] || continue
  name=$(basename "$f")
  backup_if_exists "$TARGET/scripts/$name"
  do_or_show cp "$f" "$TARGET/scripts/$name"
  case "$name" in *.sh|*.py) do_or_show chmod +x "$TARGET/scripts/$name" ;; esac
done

say "Copying shared library, tools and tests…"
for f in "$REPO_DIR"/lib/*.py; do
  [[ -f "$f" ]] || continue
  do_or_show cp "$f" "$TARGET/lib/$(basename "$f")"
done
for f in "$REPO_DIR"/bin/*; do
  [[ -f "$f" ]] || continue
  name=$(basename "$f")
  backup_if_exists "$TARGET/bin/$name"
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
  for f in "$TARGET"/bin/*; do
    [[ -e "$HOME/.local/bin/$(basename "$f")" && ! -L "$HOME/.local/bin/$(basename "$f")" ]] && { warn "~/.local/bin/$(basename "$f") exists and is not ours — left alone"; continue; }
    do_or_show ln -sfn "$f" "$HOME/.local/bin/$(basename "$f")"
  done
  case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) warn "add ~/.local/bin to PATH for the tools (secret-scan, swap-live, creds, rename-ref)" ;; esac
fi

say "Copying skills…"
for d in "$REPO_DIR"/skills/*/; do
  [[ -d "$d" ]] || continue
  name=$(basename "$d")
  backup_if_exists "$TARGET/skills/$name"
  do_or_show cp -r "$d" "$TARGET/skills/$name"
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

say "Copying memory template…"
if [[ ! -f "$TARGET/memory/MEMORY.md" ]]; then
  do_or_show cp -r "$REPO_DIR/memory-template/"* "$TARGET/memory/"
  ok "memory initialized from template"
else
  warn "memory/MEMORY.md already exists — not overwritten. See $REPO_DIR/memory-template/ for reference."
fi

# ---- generate settings.json ---------------------------------------------
say "Generating settings.json…"
SETTINGS="$TARGET/settings.json"
backup_if_exists "$SETTINGS"
# Re-running (an update) MERGES into an existing settings.json: the user's permissions, env,
# model and their own hooks stay; only the hook entries that point into $TARGET/hooks/ are replaced.

# Substitute the install target into the template
if [[ $DRY_RUN -eq 0 ]]; then
  # JSON-safe substitution: a path containing " \ | & would break a plain sed replacement
  python3 - "$REPO_DIR/settings.template.json" "$SETTINGS" "$TARGET" <<'PYSUB'
import json, sys
src, dst, target = sys.argv[1:]
# in commands the path sits inside shell double quotes → escape \ " $ ` for the shell first
sh = target.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
text = open(src).read()
text = text.replace("__CLAUDE_DIR_RAW__", json.dumps(target)[1:-1])
text = text.replace("__CLAUDE_DIR__", json.dumps(sh)[1:-1])
ours = json.loads(text)  # fail loudly if the template didn't render to valid JSON
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

# ---- mobile-bot addon (optional) ----------------------------------------
echo
say "Optional addon: mobile-bot (Telegram bridge to Claude Code)"
yn=$(ask "Install mobile-bot? (y/N)" "N")
if [[ "$yn" =~ ^[Yy]$ ]]; then
  ADDON_DIR="$TARGET/mobile-bot"
  do_or_show mkdir -p "$ADDON_DIR"
  do_or_show cp -r "$REPO_DIR/addons/mobile-bot/." "$ADDON_DIR/"   # "/." copies .env.template too (a * glob skips dotfiles)
  ok "mobile-bot installed at $ADDON_DIR"
  echo
  warn "Next: copy $ADDON_DIR/.env.template → .env, fill TELEGRAM_BOT_TOKEN/PIN/etc"
  warn "Then: see $ADDON_DIR/README.md for systemd setup"
fi

# ---- scheduled jobs (cron) ---------------------------------------------------
# One marked block in the user's crontab, replaced on every run (no duplicates; other lines untouched).
CRON_BEGIN="# >>> claude-code-methodology ($TARGET)"
CRON_END="# <<< claude-code-methodology ($TARGET)"
q() { printf '%q' "$1"; }
CRON_LINES="$CRON_BEGIN
*/10 * * * * python3 $(q "$TARGET/hooks/trash-guard.py") --measure >/dev/null 2>&1
35 4 * * * python3 $(q "$TARGET/hooks/trash-guard.py") --clean >/dev/null 2>&1
55 * * * * python3 $(q "$TARGET/hooks/abbr-guard.py") --build-vocab >/dev/null 2>&1
$CRON_END"
echo
say "Scheduled jobs: trash size/cleanup, abbreviation vocabulary"
if [[ $DRY_RUN -eq 1 ]]; then
  printf '  DRY: would put into crontab:\n%s\n' "$CRON_LINES"
elif command -v crontab >/dev/null 2>&1; then
  { crontab -l 2>/dev/null | awk -v b="$CRON_BEGIN" -v e="$CRON_END" '$0==b{skip=1;next} $0==e{skip=0;next} !skip'
    printf '%s\n' "$CRON_LINES"; } | crontab - && ok "crontab updated ($(crontab -l | grep -cF "$TARGET") lines)"
else
  warn "no crontab on this machine — add these lines to your scheduler by hand:"
  printf '%s\n' "$CRON_LINES" >&2
fi

# ---- verify: run the installed tests against the installed copies -----------
TESTS_FAILED=0
if [[ $VERIFY -eq 1 && $DRY_RUN -eq 0 ]] && compgen -G "$TARGET/tests/*-test.*" >/dev/null; then
  echo
  say "Checking the installed mechanisms (each test runs in a temp sandbox)…"
  for t in "$TARGET"/tests/*-test.*; do
    case "$t" in *.py) runner=python3 ;; *.sh) runner=bash ;; *) continue ;; esac
    if out=$("$runner" "$t" 2>&1); then
      ok "$(printf '%s\n' "$out" | tail -1)"
    else
      TESTS_FAILED=$((TESTS_FAILED + 1))
      warn "$(basename "$t") FAILED:"; printf '%s\n' "$out" | tail -8 >&2
    fi
  done
fi

# ---- done ---------------------------------------------------------------
echo
if [[ $TESTS_FAILED -gt 0 ]]; then
  warn "Installed, but $TESTS_FAILED test(s) failed — see above. The failing mechanism may not work on this machine."
else
  ok "Install complete."
fi
echo
echo "Checking the installation item by item…"
if [[ $DRY_RUN -eq 0 ]]; then
  if [[ "$SCOPE" == "user" ]]; then CHECK=(--user); else CHECK=(--project "$PROJECT_DIR"); fi
  python3 "$REPO_DIR/check-install.py" "${CHECK[@]}" | tail -n 4 || warn "Some items are missing — see above: python3 $REPO_DIR/check-install.py ${CHECK[*]}"
fi
echo
echo "Next steps:"
echo "  1) Review $TARGET/CLAUDE.md — edit to fit"
echo "  2) Start a new Claude Code session (existing sessions won't pick up the new config)"
echo "  3) Read $REPO_DIR/docs/architecture.md"
echo
echo "To undo: in $TARGET, restore the *.bak-${TIMESTAMP} copies over the files they back up, and remove"
echo "what this repo added (hooks/, scripts/, skills/, code-pitfalls/, lib/, bin/, mcp/, tests/, methodology.conf,"
echo ".methodology-installed/), the ~/.local/bin links to bin/ and the marked block in crontab -l."
echo "Do NOT delete $TARGET as a whole: it also holds your own Claude Code settings, memory and history."
[[ $TESTS_FAILED -eq 0 ]] || exit 3
