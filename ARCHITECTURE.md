# Architecture

Four independent parts, connected only through files:

```
 audio (mix + stems)
        │
 [1] analysis service (Python)      decode · sync · tempo/beats · transcribe
        │  writes
 [2] project manifest (JSON)        events + timing + metadata + uncertainty
        │  read by
 [3] exporters (Python)             Standard MIDI Files · aligned WAV stems · tempo map
        │  read by
 [4] Live bridge (Max for Live JS)  builds tracks, arrangement clips, notes via the LOM
```

## Principles
- **Layers, not overwrites.** The manifest keeps a `raw` layer (model output,
  never edited) and a `corrections` layer (user edits). The view you hear is
  computed from both, so every note can be traced to "detected" or "manual".
- **Time is stored in seconds from the start of the original file.** Beats and
  bars are derived from the tempo map, so correcting the tempo never moves a note
  in absolute time.
- **Uncertainty is data.** Each note carries the method, model version and a
  confidence value.
- **The bridge is thin.** The Max for Live device only reads files and calls the
  documented Live Object Model; all logic stays in Python.
- **Always a fallback.** If Live automation fails, the exporter's MIDI + WAV +
  instructions package is enough to build the Set by hand.

## Live Object Model calls in use (verified on Live 12.0.15 in Sprint 0 — see TEST_RESULTS.md)
| Need | LOM call | Since |
|---|---|---|
| New tracks | `Song.create_midi_track(i)`, `Song.create_audio_track(i)` | — |
| Arrangement MIDI clip | `Track.create_midi_clip` ❌ on 12.0.15 → **use** `ClipSlot.create_clip` + `add_new_notes` + `Track.duplicate_clip_to_arrangement` ✅ | — |
| Arrangement audio clip | `Track.create_audio_clip(path, position)` ✅ | 12.0.15 |
| Write notes | `Clip.add_new_notes({notes:[…]})` | Live 11 |
| Read notes | `Clip.get_notes_extended(...)` | Live 11 |
| Tempo | `Song.tempo` | — |
| **Save the Set** | **not in the LOM — user presses ⌘S** | — |

## Project manifest (`project.json`, v1)
Defined and documented in `mrs/manifest.py`. In short:
- `sources[]`: each file with its role (mix, vocals, bass, drums, melody,
  other), format, sample rate, length, sha256, and `sync` (offset against the
  mix, plus confidence).
- `timing.detected` is written only by analysis. `timing.correction` is
  written only by the user. `effective_timing()` merges them and labels every
  value `detected` or `manual`.
- `tracks[]` is reserved for transcription layers (Sprint 1b).

## Input: NI Stems (`.stem.mp4`, e.g. Traktor)
An open format: one MP4 with 5 audio streams (the mix plus 4 stems) on one
timeline. Stem names come from the `moov/udta/stem` JSON box. `mrs/nistem.py`
unpacks it to 24-bit WAV with ffmpeg, so the stems are sample-aligned by
construction (measured: 0.0 ms).

## Python modules
| module | job |
|---|---|
| `mrs/audio.py` | decode (libsndfile, with ffmpeg as fallback) + inspect |
| `mrs/nistem.py` | NI Stems unpacking |
| `mrs/sync.py` | stem offset vs mix (waveform cross-correlation) |
| `mrs/tempo.py` | tempo, beats, first downbeat, beat grid |
| `mrs/project.py` | song folder → manifest; summary; click-check render |
| `mrs/manifest.py` | the file format |
| `mrs/testsong.py` | synthetic song with exact ground truth |
