# HOJA DE COCA — MIDI versus drum waveform (checkpoint 4)

## Scope
Direct read of the user-provided `HOJA DE COCA TECH HOUSE(1).zip`. Analyzed the original 48 kHz drums WAV and the `drums.raw.notes` array in `project.json` (754 note starts). No modification of MIDI or audio, no Live test, no expensive ML inference.

## Method
- Stereo drums WAV downmixed to mono; 5 ms non-overlapping RMS energy windows.
- Positive frame-to-frame RMS rise, then SciPy peak detection with 100 ms minimum separation and prominence threshold 1.5× the 75th percentile of the energy-rise series.
- For each raw MIDI drum start, calculate the absolute distance to its nearest detected energy-rise peak.
- Results are *nearest-neighbor timing diagnostics*, not verified event matches. Peaks can come from other instruments, and a single peak may match multiple MIDI notes. The 5 ms windowing also limits precision.

## Results
- WAV sample rate: 48,000 Hz; duration: 156.03 s.
- Energy-rise peaks found: 942; raw drum MIDI notes: 754.

| Drum class | MIDI notes | Median nearest-peak distance | 90th percentile | Within 20 ms |
|---|---:|---:|---:|---:|
| kick | 162 | 10.9 ms | 64.7 ms | 67.9% |
| snare | 263 | 3.3 ms | 45.2 ms | 82.1% |
| closed_hat | 312 | 2.7 ms | 44.1 ms | 88.1% |
| open_hat | 4 | 2.0 ms | 5.6 ms | 100.0% |
| unclassified | 13 | 5.1 ms | 42.5 ms | 76.9% |

## Interpretation
The kick class has the largest median nearest-peak distance and lowest share within 20 ms. This **does not establish** that kick MIDI is late or wrong: low-frequency kick attacks can peak later than the physical onset, and competing snare/hat peaks make nearest-neighbor comparisons ambiguous. The existing drum MIDI was itself detected from this audio, so the comparison is not independent ground truth.

## Next bounded validation
1. Band-limit the drum audio into kick / snare / hat regions, and detect *onset starts* (not just RMS peak times).
2. Perform one-to-one matching with a bounded tolerance; report signed offsets, unmatched notes and unmatched onsets by class and by early/middle/late song region.
3. Create reproducible regression fixtures before changing the detector or export.
4. Preserve raw notes and working Ableton bridge; seek a Mac listening A/B before accepting timing corrections.

## Usage
Single-pass local signal processing, low–medium relative effort. Weekly quota percentage unavailable.
