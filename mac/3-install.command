#!/bin/bash
# Sprint 1a — install the analysis tools, test them on this Mac, and look for
# Traktor stem files. Safe to run again: it skips what is already installed.
#
# Installs (via Homebrew): uv (Python manager) and a current ffmpeg.
# Creates: .venv/ inside this project folder (Python 3.11 + Basic Pitch etc.)
# Reads only: your Music / Documents / Library folders, to find Traktor stems.
# It never moves, changes or uploads your audio.

cd "$(dirname "$0")/.." || exit 1
mkdir -p reports/sprint1
REPORT="reports/sprint1/mac-install.txt"
SCAN="reports/sprint1/traktor-scan.txt"
BREW="$(command -v brew || echo /opt/homebrew/bin/brew)"

echo "== 1/5 Homebrew tools (uv, ffmpeg) — may take a few minutes the first time"
for pkg in uv ffmpeg; do
  if "$BREW" list --versions $pkg >/dev/null 2>&1; then echo "  $pkg already installed"; else "$BREW" install $pkg; fi
done
export PATH="$("$BREW" --prefix)/bin:$PATH"   # Homebrew's ffmpeg before the 2015 one

echo "== 2/5 Python 3.11 environment + packages (first time: ~1 GB download)"
[ -d .venv ] || uv venv -p 3.11 .venv
uv pip install -p .venv/bin/python -r requirements.txt

{
echo "# MRS Sprint 1a — Mac install report"
echo "date: $(date '+%Y-%m-%d %H:%M:%S %z')"
echo "python: $(.venv/bin/python --version 2>&1)"
echo "ffmpeg: $(ffmpeg -version 2>&1 | head -1)  ($(command -v ffmpeg))"
echo "uv: $(uv --version 2>&1)"
echo
echo "## Key packages"
uv pip freeze -p .venv/bin/python 2>/dev/null | grep -iE "^(basic-pitch|coremltools|tensorflow|numpy|librosa|soundfile|onnxruntime|scipy)="
echo
echo "## Unit + integration tests (pytest)"
} > "$REPORT"

echo "== 3/5 Running the tests on this Mac"
.venv/bin/python -m pytest -q -W ignore tests 2>&1 | tail -15 | tee -a "$REPORT"

echo "== 4/5 Basic Pitch on this Mac (transcription probe)"
{ echo; echo "## Transcription probe"; } >> "$REPORT"
/usr/bin/time -l .venv/bin/python tools/probe_transcription.py 2>&1 \
  | grep -E "^(bass|melody|peak)|Error|error|maximum resident|real" | tail -12 | tee -a "$REPORT"

echo "== 5/5 Looking for Traktor stem files (read-only)"
{
echo "# Traktor / NI Stems scan — $(date '+%Y-%m-%d %H:%M')"
echo
echo "## .stem.mp4 / .stem.m4a files (first 40)"
find "$HOME" -type f \( -iname "*.stem.mp4" -o -iname "*.stem.m4a" \) 2>/dev/null | head -40
echo "total: $(find "$HOME" -type f \( -iname "*.stem.mp4" -o -iname "*.stem.m4a" \) 2>/dev/null | wc -l | tr -d ' ')"
echo
echo "## Traktor 4 stem cache (~/Music/Traktor/Stems): count, size, first 25 titles"
TS="$HOME/Music/Traktor/Stems"
if [ -d "$TS" ]; then
  echo "files: $(find "$TS" -name '*.stem.mp4' | wc -l | tr -d ' ')   size: $(du -sh "$TS" | cut -f1)"
  find "$TS" -name '*.stem.mp4' | head -25 | while read -r f; do
    t="$(ffmpeg -hide_banner -i "$f" 2>&1 | grep -m2 -E '^\s+(title|artist)\s*:' | sed -E 's/^ +//' | tr '\n' ' ')"
    echo "  $(basename "$f")  ->  $t"
  done
else
  echo "not found"
fi
echo
echo "## Traktor / Native Instruments folders and sizes"
for base in "$HOME/Documents/Native Instruments" "$HOME/Library/Application Support/Native Instruments" \
            "$HOME/Library/Caches/Native Instruments" "$HOME/Library/Caches" "$HOME/Music"; do
  [ -d "$base" ] || continue
  find "$base" -maxdepth 3 -type d \( -iname "*traktor*" -o -iname "*stem*" \) 2>/dev/null | while read -r d; do
    echo "$(du -sh "$d" 2>/dev/null | cut -f1)	$d"
  done
done
echo
echo "## Inside folders named *stem* or *cache* under Traktor: file types and counts"
find "$HOME/Documents/Native Instruments" "$HOME/Library/Application Support/Native Instruments" \
     "$HOME/Library/Caches" -maxdepth 6 -type d \( -iname "*stem*" -o -ipath "*traktor*cache*" \) 2>/dev/null | head -20 | while read -r d; do
  echo "-- $d"
  find "$d" -maxdepth 2 -type f 2>/dev/null | sed -E 's/.*\.([^./]+)$/\1/' | sort | uniq -c | sort -rn | head -5
  echo "   newest: $(ls -t "$d" 2>/dev/null | head -3 | tr '\n' ' ')"
done
} > "$SCAN" 2>&1
cat "$SCAN" | head -40

echo
echo "------------------------------------------------------------"
"$(dirname "$0")/_send-results.sh" "Sprint 1a: Mac install, tests and Traktor scan"
