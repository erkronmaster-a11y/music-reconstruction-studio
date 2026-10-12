#!/bin/bash
# Sprint 3 — send the Loomback Builder reports (reports/sprint3/live-*.json).
cd "$(dirname "$0")/.." || exit 1
for f in reports/sprint3/live-build.json reports/sprint3/live-verify.json; do
  if [ -f "$f" ]; then echo "found: $f"; else echo "MISSING: $f (did you click build / verify in the device?)"; fi
done
"$(dirname "$0")/_send-results.sh" "Sprint 3: Ableton build results"
