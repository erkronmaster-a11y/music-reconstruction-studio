# HOJA DE COCA TECH HOUSE — timing metadata checkpoint 2

Scope: inspected the user's supplied ZIP `HOJA DE COCA TECH HOUSE(1).zip`, specifically `project.json` and `midi/export.json`. **This is not yet an independent waveform-onset or listening test.**

## Observed values
- Global detected tempo: **100.075 BPM**.
- Detected first downbeat: **0.1089 s**.
- Detected tempo stability metric: **0.101** (as recorded by the existing detector; not an independent accuracy score).
- A detected `beat_map` exists with raw/smoothed beat arrays, local tempo range and irregular-bar information.
- All four stems (other, bass, drums, vocals) have saved `offset_s: 0.0`; their GCC-PHAT confidence values are respectively **0.324, 0.644, 0.704, 0.243**. These are algorithm outputs, not independently confirmed alignments.
- MIDI export uses `mode: constant`, `tempo_bpm: 100.075`, `pad_s: 2.289301`, `shift_beats: 0`, `first_downbeat_bar: 2`.
- All five audio files (mix and four stems) have export placement `start_s: 2.289301` and `warp: false`.

## Interpretation
The exported constant tempo intentionally keeps all audio files at natural playback speed, while MIDI follows the same global seconds-to-beats transform. The existing variable beat map is not being applied to Warp in this export. Therefore the presence of a beat map alone is not evidence that source timing irregularities were corrected. The 2.289301-second padding is consistent with the first downbeat being aligned to the next full bar, not by itself proof of a bug.

## Next measurable task
Read WAV drum-stem transients, compare them to candidate stable grids and the saved beat map over early/middle/late sections, and report robust deviation distributions. Separate source timing jitter, progressive drift, and exported placement offset. Do not alter the working Ableton bridge or auto-quantize notes before this measurement.

## Usage boundary
Checkpoint 2 stops at metadata inspection. No long audio inference, Live automation or expensive test suite was run.
