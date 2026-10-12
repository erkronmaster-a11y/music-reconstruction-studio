#!/bin/bash
# Sprint 0, step 3 — send the Ableton test results (reports/sprint0/live-*.json).
cd "$(dirname "$0")/.." || exit 1
for f in reports/sprint0/live-create.json reports/sprint0/live-verify.json; do
  if [ -f "$f" ]; then echo "found: $f"; else echo "MISSING: $f (did you click run / verify in the device?)"; fi
done
"$(dirname "$0")/_send-results.sh" "Sprint 0: Ableton Live API test results"
