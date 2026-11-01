# HOJA DE COCA — frequency-separated onset diagnostic (checkpoint 5)

## Input and processing
- Directly analyzed the user's original `HOJA DE COCA TECH HOUSE(1).zip` and the 48,000 Hz drums stem (156.0307 seconds).
- Compared the `drums.raw.notes` in `project.json` with independent band-pass energy-rise candidates.
- Bands: kick 35–160 Hz; snare 170–2400 Hz; hats 3500–11000 Hz. Third-order Butterworth filters, 5 ms nonoverlapping RMS windows, positive RMS differences, adaptive peak thresholds, 70 ms peak separation.
- Greedy globally closest **one-to-one** candidate assignment within ±60 ms, separately for each drum class. No sample-accurate onset labeling, ground-truth identity, or source separation.
- Positive signed offset means the detected energy-rise peak is later than the MIDI note start.

## Results
| Class | MIDI notes | Candidate onsets in band | Matched notes | Median signed offset | Median absolute offset | P90 absolute offset |
|---|---:|---:|---:|---:|---:|---:|
| kick | 162 | 509 | 162 | +4.7 ms | 4.7 ms | 20.3 ms |
| snare | 263 | 733 | 263 | -2.0 ms | 2.5 ms | 4.2 ms |
| closed_hat | 312 | 635 | 312 | -2.5 ms | 2.5 ms | 4.1 ms |
| open_hat | 4 | 635 | 3 | -1.8 ms | 1.8 ms | 2.1 ms |

Median signed offsets across successive 52-second regions:
- Kick: +3.9, +5.2, +4.5 ms (67 / 51 / 44 matches).
- Snare: -1.9, -2.2, -2.2 ms (124 / 72 / 67 matches).
- Closed hat: -2.3, -2.6, -2.6 ms (89 / 129 / 94 matches).

## Interpretation / caveats
- This more targeted diagnostic does **not** show a clear progressive offset trend in matched kick events.
- The high match counts must **not** be described as verified transcription recall or precision: broad bands contain overlapping instruments, and there are substantially more candidate peaks than MIDI events.
- Band-pass filters and 5 ms RMS framing affect onset phase; offsets cannot yet be treated as corrections.
- The four open-hat notes are too few for robust inference.
- No MIDI edits, quantization, Ableton bridge edits, or automatic kick shifts are justified by this test.

## Next bounded checkpoint
- Create a reproducible local diagnostic script with explicit peak selection and one-to-one matching.
- Validate against synthetic isolated kicks/snares/hats with known onset times and overlap.
- Then compare unmatched candidates and MIDI events in real audio; audition representative kick outliers in Ableton.
- Preserve original source timing and English-only product language.

## Usage
Bounded local signal processing; account usage meter unavailable.
