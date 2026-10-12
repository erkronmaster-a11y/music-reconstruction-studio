#!/bin/bash
# Loomback by SMV — opens the app in your browser. Keep this window open while
# you use it; close it (or press Ctrl+C) to quit. Everything stays on this Mac.
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
[ -x .venv/bin/python ] || { echo "Run mac/3-install.command first."; read -r -p "Press Enter to close." _; exit 1; }
git pull -q 2>/dev/null && echo "(updated to the latest version)"
.venv/bin/python -m mrs.gui.server
