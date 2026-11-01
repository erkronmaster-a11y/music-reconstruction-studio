# HOJA DE COCA — direct audio timing measurement (checkpoint 3)

## Inputs and method
- User-supplied `HOJA DE COCA TECH HOUSE(1).zip`, `project.json`, and the original 48 kHz drum stem.
- 256 smoothed beat timestamps from the saved Beat This! map, fitted with least-squares linear regression against beat positions.
- Direct waveform analysis: 5 ms RMS windows, positive energy differences, peak picking with 100 ms minimum separation and a relative energy threshold. **This is a diagnostic transient detector, not ground-truth drum transcription.**
- Compare transient times to nearest sixteenth-note position on the fitted constant grid and to interpolated saved beat-map grid.

## Measured results
| Metric | Result |
|---|---:|
| Saved export tempo | 100.075 BPM |
| Beat-map linear-fit tempo | 99.998485 BPM |
| Beat-map fit intercept | 0.057182 s |
| Beat-map beats | 256 |
| Median absolute beat-map residual from straight grid | 1.48 ms |
| 90th-percentile absolute beat-map residual | 2.74 ms |
| Maximum absolute beat-map residual | 38.99 ms |
| Saved beat-map local BPM 5th–95th percentiles | 99.6–100.4 |
| Detected drum energy-rise peaks | 553 |
| Constant-grid transient nearest-16th median absolute deviation | 13.56 ms |
| Constant-grid transient nearest-16th 90th percentile | 63.16 ms |
| Beat-map transient nearest-16th median absolute deviation | 15.00 ms |
| Beat-map transient nearest-16th 90th percentile | 65.00 ms |
| Constant-grid transient share within 20 ms | 76.5% |
| Beat-map transient share within 20 ms | 77.8% |

Beat-map residual medians by track region (against globally fitted straight grid): early 2.22 ms; middle 1.50 ms; late 0.79 ms. The 38.99 ms maximum warrants inspection; it does not by itself prove an intentional timing event or a detector mistake.

## Interpretation and limitations
- The beat map is predominantly close to a stable ~100 BPM grid. The global tempo exported as 100.075 BPM differs by about 0.0765 BPM; over 156 s this represents roughly 0.199 beats, or ~119 ms, of relative grid phase divergence. This is **relative to the fitted grid**, not proof that audio and MIDI export are out of sync with one another.
- Some transient peaks are intentionally offbeat, are not drums, are soft-attack events, or are detector artifacts. The 16th-note residuals are **not** a musical accuracy score.
- This test does not establish the absolute downbeat phase or correct which tempo should be authoritative for the song. Neither Live playback nor actual MIDI-note timing has yet been independently verified.
- Existing Ableton bridge and export code were **not changed**.

## Proposed next bounded task
1. Verify drum MIDI hit times against detected original drum onsets in the same source timeline (not against a presumed quantized grid).
2. Inspect the 39 ms beat-map outlier and 7 irregular-bar flags for detector mistakes versus real musical events.
3. Add deterministic regression fixtures and an optional tempo-review warning before changing export tempo or quantization behavior.
4. Require Mac/Live A/B validation before changing the bridge.

## Usage
Bounded single-pass signal processing; no expensive ML inference. Account-level usage percentage cannot be measured here.
