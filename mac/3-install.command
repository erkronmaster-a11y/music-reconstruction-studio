#!/bin/bash
# Sprint 1a — install the analysis tools, test them on this Mac, and look for
# Traktor stem files. Safe to run again: it skips what is already installed.
#
# Installs (via Homebrew): a current ffmpeg (and Python 3.11 only if missing).
# Creates: .venv/ inside this project folder (Python 3.11 + Basic Pitch etc.)
# Reads only: your Music / Documents / Library folders, to find Traktor stems.
# It never moves, changes or uploads your audio.

cd "$(dirname "$0")/.." || exit 1
mkdir -p reports/sprint1
REPORT="reports/sprint1/mac-install.txt"
SCAN="reports/sprint1/traktor-scan.txt"
BREW="$(command -v brew || echo /opt/homebrew/bin/brew)"

echo "== 1/5 ffmpeg (via Homebrew)"
# Only ffmpeg comes from Homebrew. (uv was dropped: on macOS 13, Homebrew
# could not install it — "Tier 3 configuration".)
if "$BREW" list --versions ffmpeg >/dev/null 2>&1; then echo "  ffmpeg already installed"; else "$BREW" install ffmpeg; fi
export PATH="$("$BREW" --prefix)/bin:$PATH"   # Homebrew's ffmpeg before the 2015 one

echo "== 2/5 Python 3.11 environment + packages (first time: ~1 GB download)"
PY=""
for c in python3.11 "$HOME/.local/bin/python3.11" /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; assert sys.version_info[:2]==(3,11)' 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "  Python 3.11 not found — installing it with Homebrew"
  "$BREW" install python@3.11 && PY="$("$BREW" --prefix)/bin/python3.11"
fi
echo "  using $PY"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

{
echo "# MRS Sprint 1a — Mac install report"
echo "date: $(date '+%Y-%m-%d %H:%M:%S %z')"
echo "python: $(.venv/bin/python --version 2>&1)"
echo "ffmpeg: $(ffmpeg -version 2>&1 | head -1)  ($(command -v ffmpeg))"
echo "python_used_for_venv: $PY"
echo
echo "## Key packages"
.venv/bin/python -m pip freeze 2>/dev/null | grep -iE "^(basic-pitch|coremltools|tensorflow|numpy|librosa|soundfile|onnxruntime|scipy)="
echo
echo "## Unit + integration tests (pytest)"
} > "$REPORT"

[ -x .venv/bin/python ] || { echo "Python environment missing — stopping. Send Claude a screenshot."; read -r -p "Press Enter to close." _; exit 1; }
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
echo "## .stem.mp4 / .stem.m4a outside the Traktor cache (Music, Documents, Desktop, Downloads; first 40)"
WHERE=("$HOME/Music" "$HOME/Documents" "$HOME/Desktop" "$HOME/Downloads")
find "${WHERE[@]}" -maxdepth 6 -type f \( -iname "*.stem.mp4" -o -iname "*.stem.m4a" \) -not -path "*/Traktor/Stems/*" 2>/dev/null | head -40
echo
echo "## Traktor 4 stem cache — titles from Traktor's collection.nml (newest first, first 40)"
.venv/bin/python -m mrs traktor-list 2>&1 | head -42
echo
echo "## How collection.nml refers to one stem file (to check the title lookup)"
.venv/bin/python - <<'PY' 2>&1
from pathlib import Path
from mrs import nistem
nml = nistem.traktor_collections()
files = sorted((Path.home() / "Music/Traktor/Stems").rglob("*.stem.mp4"))
if not nml or not files:
    print("collection.nml or stem files not found")
else:
    text = nml[0].read_text(errors="replace")
    for f in files[:50]:
        i = text.find(f.name[:-9])
        if i >= 0:
            print(text[max(0, i - 600):i + 200]); break
    else:
        print("none of the first 50 stem codes appear in", nml[0])
PY
echo
echo "## Traktor / Native Instruments folders and sizes"
for base in "$HOME/Documents/Native Instruments" "$HOME/Library/Application Support/Native Instruments" \
            "$HOME/Library/Caches/Native Instruments" "$HOME/Music"; do
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
