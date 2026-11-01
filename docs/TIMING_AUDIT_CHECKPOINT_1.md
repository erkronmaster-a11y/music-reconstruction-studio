# Loomback timing audit — checkpoint 1

Status: source-code audit only. No audio measurements or Mac/Ableton regression tests performed in this checkpoint.

## Findings
1. `mrs/export.py` and `mrs/liveplan.py` share `raw_beats` / `timeline` mapping, so constant-mode audio and MIDI placement is intended to be consistent. This does **not** straighten source-audio timing irregularities.
2. `mrs/beatmap.py` provides a per-beat time map, gap repair and smoothing, but `mrs/export.py` enables per-beat mode only when `timing.warp_per_beat` is explicitly set and no manual timing correction exists.
3. The code documents Live 12.0.15 rejecting added warp markers. Thus per-beat audio correction is not a proven available path on the owner's Live setup. Preserve the existing Live bridge until separately tested.
4. `mrs/tempo.py` derives a global tempo from an onset comb, and `mrs/beatmap.py` rounds beats to 0.1 ms and smooths by up to 12 ms. Neither is a sample-index source of truth. A new timing representation should preserve original detected events and integer sample indices, with corrections stored separately.
5. `mrs/liveplan.py` rounds MIDI beat positions to five decimals. At 100 BPM that is ~0.006 ms resolution; nevertheless test full export/import round trips rather than assuming Live playback is exact.
6. The existing `tests/test_sprint1a.py` includes synthetic tempo/drift checks. Keep these and add tests for nonuniform tempo, offsets, source-vs-grid timing, and Live-plan vs MIDI parity.

## Proposed next checkpoint (requires user feedback after test)
- Inspect HOJA DE COCA audio/MIDI package and measure transient-to-grid deviations across the whole track, independently of exported MIDI.
- Quantify offset, global tempo mismatch, progressive drift, and local jitter separately.
- Save a report with measured error distributions and confidence; do not auto-quantize or change the Ableton bridge.
- Only then implement a deterministic correction layer, retaining raw timings and a reversible Strict Grid / Groove Preservation choice.

## Preservation
Do not replace `live/loomback_build.js`, `live/mrs_bridge.js`, or the AMXD builder without a verified failing test. No code changes were made to these components in this checkpoint.

## Usage policy
Checkpoint is intentionally bounded; no numerical usage percentage can be asserted without account telemetry.
