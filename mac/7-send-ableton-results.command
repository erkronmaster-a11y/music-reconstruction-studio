#!/bin/bash
# Sprint 3 — send the Loomback Builder reports.
# The device saves them in ~/Music/MRS Projects/_live/ (and in reports/sprint3/ when it can).
cd "$(dirname "$0")/.." || exit 1
mkdir -p reports/sprint3
for n in live-build.json live-verify.json; do
  src="$HOME/Music/MRS Projects/_live/$n"
  [ -f "$src" ] && cp "$src" "reports/sprint3/$n"
  [ -f "reports/sprint3/$n" ] || { [ -f "/tmp/loomback/$n" ] && cp "/tmp/loomback/$n" "reports/sprint3/$n"; }
  if [ -f "reports/sprint3/$n" ]; then echo "found: $n"; else echo "MISSING: $n (did you click build / verify in the device?)"; fi
done
"$(dirname "$0")/_send-results.sh" "Sprint 3: Ableton build results"
