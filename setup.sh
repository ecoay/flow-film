#!/usr/bin/env bash
# Installs flow-film on a Debian/Ubuntu Linux box. Safe to re-run.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
SUDO=""; [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null && SUDO="sudo"
need_apt=()
command -v ffmpeg >/dev/null || need_apt+=(ffmpeg)
command -v espeak-ng >/dev/null || need_apt+=(espeak-ng)
command -v python3 >/dev/null || need_apt+=(python3 python3-pip)
if [ ${#need_apt[@]} -gt 0 ]; then $SUDO apt-get update -q && $SUDO apt-get install -y -q "${need_apt[@]}"; fi
if ! command -v google-chrome >/dev/null && ! command -v google-chrome-stable >/dev/null && ! command -v chromium >/dev/null && [ -z "${FLOWFILM_CHROME:-}" ]; then
  echo "Installing Google Chrome..."
  tmp=$(mktemp -d); curl -fsSL -o "$tmp/chrome.deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  $SUDO apt-get install -y -q "$tmp/chrome.deb"
fi
python3 -c "import playwright" 2>/dev/null || python3 -m pip install -q --break-system-packages playwright pytest \
  || python3 -m pip install -q playwright pytest
mkdir -p "$HOME/.local/bin"; ln -sf "$DIR/flowfilm.sh" "$HOME/.local/bin/flowfilm"
echo "Checking..."; "$DIR/flowfilm.sh" moves >/dev/null && echo "flow-film ready: run 'flowfilm login' and sign in to Google in the Chrome window."
