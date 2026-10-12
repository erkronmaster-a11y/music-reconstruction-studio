#!/bin/bash
# Loomback by SMV — opens the app in your browser. Keep this window open while
# you use it; close it (or press Ctrl+C) to quit. Everything stays on this Mac.
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
[ -x .venv/bin/python ] || { echo "Run mac/3-install.command first."; read -r -p "Press Enter to close." _; exit 1; }
git pull -q 2>/dev/null && echo "(updated to the latest version)"
# A Loomback left running (or stuck) from before still holds the port: stop it.
OLD=$(lsof -ti tcp:8765 2>/dev/null)
if [ -n "$OLD" ]; then echo "Stopping an earlier Loomback (pid $OLD)…"; kill $OLD 2>/dev/null; sleep 1; fi
LOG="$HOME/Music/MRS Projects/_loomback.log"
mkdir -p "$HOME/Music/MRS Projects"
.venv/bin/python -m mrs.gui.server 2>&1 | tee -a "$LOG"
echo
echo "Loomback stopped. If that was unexpected, the reason is above (also saved in $LOG)."
echo "Send Claude a screenshot of this window, then double-click Loomback.command to start again."
read -r -p "Press Enter to close." _
