#!/usr/bin/env bash
# Bootstrap installer for claude-code-methodology.
#
# Detects Claude Code, asks where to install (user vs project scope),
# copies hooks/scripts with path-rewriting, generates settings.json,
# offers optional Python deps, offers optional addons (mobile-bot).
#
# Usage:
#   ./install.sh                 # interactive
#   ./install.sh --user          # install to ~/.claude (non-interactive default)
#   ./install.sh --project DIR   # install to DIR/.claude
#   ./install.sh --dry-run       # show what would happen, do nothing
#
# Re-run safe: existing files are backed up to *.bak-<timestamp>.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DRY_RUN=0
SCOPE=""
PROJECT_DIR=""

# ---- arg parse -----------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)        SCOPE="user" ;;
    --project)     SCOPE="project"; PROJECT_DIR="${2:-}"; shift ;;
    --dry-run)     DRY_RUN=1 ;;
    -h|--help)     grep '^#' "$0" | sed 's/^# \?//'; exit 0 ;;
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
  if [[ -n "$default" ]]; then prompt="$prompt [$default]"; fi
  printf '%s: ' "$prompt"
  read -r ans
  echo "${ans:-$default}"
}

do_or_show() {
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  DRY: $*"
  else
    eval "$*"
  fi
}

# ---- detect claude-code --------------------------------------------------
say "Detecting Claude Code…"
if command -v claude >/dev/null 2>&1; then
  CLAUDE_VERSION=$(claude --version 2>/dev/null | head -1 || echo unknown)
  ok "claude CLI found: $CLAUDE_VERSION"
else
  warn "claude CLI not found in PATH. Install from https://docs.anthropic.com/claude-code and re-run."
  read -p "Continue anyway? [y/N] " yn
  [[ "$yn" =~ ^[Yy]$ ]] || exit 1
fi

# ---- choose scope --------------------------------------------------------
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
do_or_show "mkdir -p '$TARGET'/{hooks,scripts,memory}"

# ---- backup existing -----------------------------------------------------
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
backup_if_exists() {
  local path="$1"
  if [[ -e "$path" ]]; then
    do_or_show "cp -a '$path' '${path}.bak-${TIMESTAMP}'"
    warn "backed up existing $path → ${path}.bak-${TIMESTAMP}"
  fi
}

# ---- copy core files -----------------------------------------------------
say "Copying CLAUDE.md (operating core)…"
backup_if_exists "$TARGET/CLAUDE.md"
do_or_show "cp '$REPO_DIR/CLAUDE.md' '$TARGET/CLAUDE.md'"

say "Copying hooks…"
for f in "$REPO_DIR"/hooks/*.sh; do
  [[ -f "$f" ]] || continue
  name=$(basename "$f")
  backup_if_exists "$TARGET/hooks/$name"
  do_or_show "cp '$f' '$TARGET/hooks/$name'"
  do_or_show "chmod +x '$TARGET/hooks/$name'"
done

say "Copying scripts…"
for f in "$REPO_DIR"/scripts/*; do
  [[ -f "$f" ]] || continue
  name=$(basename "$f")
  backup_if_exists "$TARGET/scripts/$name"
  do_or_show "cp '$f' '$TARGET/scripts/$name'"
  case "$name" in *.sh|*.py) do_or_show "chmod +x '$TARGET/scripts/$name'" ;; esac
done

say "Copying memory template…"
if [[ ! -f "$TARGET/memory/MEMORY.md" ]]; then
  do_or_show "cp -r '$REPO_DIR/memory-template/'* '$TARGET/memory/'"
  ok "memory initialized from template"
else
  warn "memory/MEMORY.md already exists — not overwritten. See $REPO_DIR/memory-template/ for reference."
fi

# ---- generate settings.json ---------------------------------------------
say "Generating settings.json…"
SETTINGS="$TARGET/settings.json"
backup_if_exists "$SETTINGS"

# Substitute the install target into the template
if [[ $DRY_RUN -eq 0 ]]; then
  sed "s|__CLAUDE_DIR__|$TARGET|g" "$REPO_DIR/settings.template.json" > "$SETTINGS"
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
    do_or_show "sudo apt-get update -qq"
    do_or_show "sudo apt-get install -y poppler-utils lynx pandoc ffmpeg"
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
  do_or_show "mkdir -p '$ADDON_DIR'"
  do_or_show "cp -r '$REPO_DIR/addons/mobile-bot/'* '$ADDON_DIR/'"
  ok "mobile-bot installed at $ADDON_DIR"
  echo
  warn "Next: copy $ADDON_DIR/.env.template → .env, fill TELEGRAM_BOT_TOKEN/PIN/etc"
  warn "Then: see $ADDON_DIR/README.md for systemd setup"
fi

# ---- done ---------------------------------------------------------------
echo
ok "Install complete."
echo
echo "Next steps:"
echo "  1) Review $TARGET/CLAUDE.md — edit to fit"
echo "  2) Start a new Claude Code session (existing sessions won't pick up the new config)"
echo "  3) Read $REPO_DIR/docs/architecture.md"
echo
echo "To uninstall: delete $TARGET and restore *.bak-${TIMESTAMP} files."
