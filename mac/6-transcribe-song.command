#!/bin/bash
# Sprint 1b — song → bass + melody MIDI, aligned to the original audio.
#
# Drag in ONE of:
#   - a Traktor .stem.mp4 (from "Traktor stems list.txt" on your Desktop)
#   - a song folder (full mix + stems)
#   - a project folder already in ~/Music/MRS Projects/
# Output in ~/Music/MRS Projects/<song>/:
#   midi/        bass + melody MIDI (raw/ holds every detected note, unfiltered)
#   review/      "AB" files: left ear = original part, right ear = the MIDI played back
#   export.json  tempo + where to place audio/MIDI in Ableton
# Only text summaries go to GitHub — never audio or MIDI.

cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
[ -x .venv/bin/python ] || { echo "Run mac/3-install.command first."; read -r -p "Press Enter to close." _; exit 1; }
echo "Drag the .stem.mp4, song folder, or MRS project folder into this window, then press Enter:"
read -r SRC
SRC="${SRC%\"}"; SRC="${SRC#\"}"; SRC="${SRC%\'}"; SRC="${SRC#\'}"
SRC="$(echo "$SRC" | sed 's/\\ / /g; s/[[:space:]]*$//')"
[ -e "$SRC" ] || { echo "Not found: $SRC"; read -r -p "Press Enter to close." _; exit 1; }

PY=".venv/bin/python -W ignore -m mrs"
LOG="$(mktemp)"
START=$(date +%s)
{
if [ -f "$SRC/project.json" ]; then
  OUT="$SRC"
  $PY tempo "$OUT/project.json" --redetect | tail -8   # older projects: pick up the precise tempo fit
else
  $PY analyze "$SRC" --out-parent "$HOME/Music/MRS Projects" | tee "$LOG" || exit 1
  OUT="$(grep '^PROJECT_DIR=' "$LOG" | tail -1 | cut -d= -f2-)"
fi
echo "PROJECT=$OUT"
} | tee -a "$LOG"
OUT="$(grep '^PROJECT=' "$LOG" | tail -1 | cut -d= -f2-)"
[ -f "$OUT/project.json" ] || { echo "Analysis failed — screenshot this window for Claude."; read -r -p "Press Enter to close." _; exit 1; }

echo "== Transcribing (a full song takes a few minutes)…"
/usr/bin/time -l $PY transcribe "$OUT/project.json" 2>&1 | tee -a "$LOG" | grep -vE "^\s+[0-9]+\s+[a-z]" 
echo "== Writing MIDI + review audio…"
$PY export "$OUT/project.json" 2>&1 | tee -a "$LOG"

NAME="$(basename "$OUT")"; SAFE="$(echo "$NAME" | tr -c 'A-Za-z0-9._-' '_')"
{
  echo "# Transcription run — $NAME — $(date '+%Y-%m-%d %H:%M')"
  echo "total_seconds: $(( $(date +%s) - START ))"
  grep -E "maximum resident set size" "$LOG" | head -1 | awk '{printf "peak_memory_MB: %d\n", $1/1048576}'
  echo
  cat "$OUT/summary.txt"
  echo
  grep -E "^(bass|melody):|MIDI →|Tempo |^  (bass|melody):" "$LOG"
  echo
  echo "## review.json"; cat "$OUT/review/review.json" 2>/dev/null
} > "reports/sprint1/transcribe-$SAFE.txt"

open "$OUT/midi"; open "$OUT/review"
echo
echo "Listen to the 'AB' files in review/ with headphones: left = original, right = MIDI."
echo "Then drag the .mid files from midi/ into Ableton (see export.json for the offset)."
"$(dirname "$0")/_send-results.sh" "Sprint 1b: transcription run for $NAME"
