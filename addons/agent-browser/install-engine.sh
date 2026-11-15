#!/usr/bin/env bash
# Installs the pinned browser engine (agent-browser) into ./engine/agent-browser: one binary, ~18 MB, no browser download.
# Needs node + npm (only to fetch the package; nothing from it runs). No root needed. Idempotent. --dry-run prints the plan.
set -euo pipefail
VER=${AGENT_BROWSER_VERSION:-0.39.0}
here=$(dirname "$(readlink -f "$0")")
dry=0; [ "${1:-}" = "--dry-run" ] && dry=1
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) plat=linux-x64 ;;
  Linux-aarch64|Linux-arm64) plat=linux-arm64 ;;
  Darwin-arm64) plat=darwin-arm64 ;;
  Darwin-x86_64) plat=darwin-x64 ;;
  *) echo "install-engine: unsupported platform $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac
echo "engine: agent-browser@$VER ($plat) -> $here/engine/agent-browser"
if [ -x "$here/engine/agent-browser" ] && [ "$("$here/engine/agent-browser" --version 2>/dev/null | awk '{print $NF}')" = "$VER" ]; then
  echo "engine already at $VER - nothing to do"; exit 0
fi
if [ $dry = 1 ]; then echo "[dry-run] would: npm pack agent-browser@$VER into a temp dir, extract package/bin/agent-browser-$plat, install -m 755 it to $here/engine/agent-browser"; exit 0; fi
command -v npm >/dev/null || { echo "install-engine: npm not found - install Node.js first" >&2; exit 1; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT   # temp dir created by this run, removed by this run
( cd "$tmp" && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 PUPPETEER_SKIP_DOWNLOAD=1 npm pack --silent "agent-browser@$VER" >/dev/null \
  && tar xzf "agent-browser-$VER.tgz" "package/bin/agent-browser-$plat" )
mkdir -p "$here/engine"
install -m 755 "$tmp/package/bin/agent-browser-$plat" "$here/engine/agent-browser"
"$here/engine/agent-browser" --version
