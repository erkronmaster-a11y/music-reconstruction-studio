#!/bin/bash
# Sprint 0, step 1 — inspect this Mac and send the report to GitHub.
# Double-click in Finder. Changes nothing on your system: it only reads
# information and writes reports/sprint0/mac-env.txt inside this folder.

cd "$(dirname "$0")/.." || exit 1
OUT="reports/sprint0/mac-env.txt"
mkdir -p reports/sprint0

{
echo "# MRS Sprint 0 — Mac environment report"
echo "date: $(date '+%Y-%m-%d %H:%M:%S %z')"
echo
echo "## System"
echo "macos: $(sw_vers -productVersion) (build $(sw_vers -buildVersion))"
echo "arch_uname: $(uname -m)"
echo "cpu: $(sysctl -n machdep.cpu.brand_string 2>/dev/null)"
# 1 = this shell runs under Rosetta (Intel emulation) on Apple Silicon
echo "rosetta_translated: $(sysctl -n sysctl.proc_translated 2>/dev/null || echo 0)"
echo "apple_silicon: $(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)"
echo "ram_gb: $(( $(sysctl -n hw.memsize) / 1073741824 ))"
echo "disk_free_home: $(df -h "$HOME" | awk 'NR==2{print $4}')"
echo
echo "## Ableton Live"
FOUND=0
while IFS= read -r app; do
  [ -z "$app" ] && continue
  FOUND=1
  ver=$(defaults read "$app/Contents/Info" CFBundleShortVersionString 2>/dev/null)
  bid=$(defaults read "$app/Contents/Info" CFBundleIdentifier 2>/dev/null)
  arch=$(lipo -archs "$app/Contents/MacOS/"* 2>/dev/null | head -1)
  echo "live_app: $app"
  echo "  version: $ver"
  echo "  bundle_id: $bid"
  echo "  binary_archs: $arch"
  case "$app" in *Suite*) echo "  edition_from_name: Suite";; *) echo "  edition_from_name: (not in name — check About Live)";; esac
  echo "  bundled_max:"
  find "$app/Contents" -maxdepth 4 -iname "Max*.app" 2>/dev/null | sed 's/^/    /'
done < <( { ls -d /Applications/Ableton\ Live*.app "$HOME"/Applications/Ableton\ Live*.app 2>/dev/null;
            mdfind "kMDItemCFBundleIdentifier == 'com.ableton.live'" 2>/dev/null; } | sort -u )
[ $FOUND = 0 ] && echo "live_app: NOT FOUND"
echo "standalone_max: $(ls -d /Applications/Max*.app 2>/dev/null | tr '\n' ' ')"
echo "live_prefs_versions: $(ls "$HOME/Library/Preferences/Ableton" 2>/dev/null | tr '\n' ' ')"
echo "user_library: $( [ -d "$HOME/Music/Ableton/User Library" ] && echo "$HOME/Music/Ableton/User Library" || echo 'not at default location')"
# Max for Live's own settings folder exists once Max for Live has been used
echo "max8_prefs: $( [ -d "$HOME/Library/Application Support/Cycling '74/Max 8" ] && echo yes || echo no)"
echo "max9_prefs: $( [ -d "$HOME/Library/Application Support/Cycling '74/Max 9" ] && echo yes || echo no)"
echo
echo "## Developer tools"
# Checking xcode-select first: calling python3 without the Command Line Tools
# would pop up an installer, which this script must not do.
if xcode-select -p >/dev/null 2>&1; then
  echo "xcode_clt: $(xcode-select -p)"
  echo "python3: $(python3 --version 2>&1) at $(command -v python3)"
else
  echo "xcode_clt: NOT INSTALLED"
fi
for py in python3.11 python3.12 python3.13; do
  command -v $py >/dev/null && echo "$py: $($py --version 2>&1) at $(command -v $py)"
done
for tool in brew git uv ffmpeg; do
  if command -v $tool >/dev/null; then echo "$tool: $($tool --version 2>&1 | head -1)"; else echo "$tool: not installed"; fi
done
} > "$OUT" 2>&1

cat "$OUT"
echo
echo "------------------------------------------------------------"
"$(dirname "$0")/_send-results.sh" "Sprint 0: Mac environment report"
