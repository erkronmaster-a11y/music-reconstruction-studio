#!/bin/bash
# Lists Traktor's stem files (newest first) with the song each one belongs to,
# matched by exact track length against Traktor's library. Read-only.
# Also saves the list to your Desktop as "Traktor stems list.txt".
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
OUT="reports/sprint1/traktor-list.txt"
echo "Reading 184-ish files — about a minute…"
.venv/bin/python -W ignore -m mrs traktor-list | tee "$OUT"
cp "$OUT" "$HOME/Desktop/Traktor stems list.txt"
echo
echo "Saved to your Desktop: 'Traktor stems list.txt'. Drag any listed .stem.mp4 into 4-analyze-song.command."
"$(dirname "$0")/_send-results.sh" "Sprint 1a: Traktor stems list"
