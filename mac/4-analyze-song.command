#!/bin/bash
# Analyse one song: tempo, beats, first downbeat, stem alignment.
#
# Give it EITHER a folder holding the full mix + any stems
#   (the mix's file name must contain "mix", "master" or "full";
#    stems are recognised by "vocal", "drum", "bass", "melody/lead/synth"…)
# OR a Traktor / NI ".stem.mp4" file — it is unpacked into perfectly aligned WAVs.
#
# Output goes to ~/Music/MRS Projects/<song>/ . Your original files are not changed.
# Only the short text summary is sent to GitHub — never the audio.

cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
echo "Drag the song folder (or .stem.mp4 file) into this window, then press Enter:"
read -r SRC
SRC="${SRC%\"}"; SRC="${SRC#\"}"; SRC="${SRC%\'}"; SRC="${SRC#\'}"
SRC="$(echo "$SRC" | sed 's/\\ / /g; s/[[:space:]]*$//')"   # undo Terminal's drag escaping
[ -e "$SRC" ] || { echo "Not found: $SRC"; read -r -p "Press Enter to close." _; exit 1; }

if [ ! -x .venv/bin/python ]; then
  echo
  echo "The analysis tools are not installed yet."
  echo "First double-click mac/3-install.command (once, about 10 minutes), then try again."
  read -r -p "Press Enter to close." _; exit 1
fi

LOG="$(mktemp)"
if .venv/bin/python -W ignore -m mrs analyze "$SRC" --out-parent "$HOME/Music/MRS Projects" | tee "$LOG"; then
  OUT="$(grep '^PROJECT_DIR=' "$LOG" | tail -1 | cut -d= -f2-)"
  .venv/bin/python -m mrs click "$OUT/project.json"
  SAFE="$(basename "$OUT" | tr -c 'A-Za-z0-9._-' '_')"
  cp "$OUT/summary.txt" "reports/sprint1/song-$SAFE.txt"
  echo
  echo "Opening the click check: high click = bar start, low click = beat."
  echo "Does the high click land on each bar's first beat? Tell Claude yes/no."
  echo "If it drifts, also play click-follow.wav (clicks on the detected beats) and say which one stays tight."
  open "$OUT/click-check.wav"
  "$(dirname "$0")/_send-results.sh" "Sprint 1a: analysis summary for $(basename "$OUT")"
else
  echo "Analysis failed — the message above says why. Send Claude a screenshot."
  read -r -p "Press Enter to close." _
fi
