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
- `tracks[]`: one per part (`bass`, `melody`), each with:
  - `raw`: method, pitch range, source, applied sync offset, what
    "confidence" means for this method, and notes as `{start_s, end_s, pitch,
    velocity, confidence, flags?}` on the mix timeline.
  - `corrections[]`: written only by the editor (Sprint 4).
  - `effective_notes(view)`: `clean` leaves out flagged notes, `raw` keeps all.
- Sources per part: bass ← bass stem; melody ← melody stem, else the `other`
  stem. If there is no stem, the part is **skipped and reported**, never
  guessed from the full mix.

## Beat map (Sprint 1c)
`mrs/beatmap.py`. Early AI songs drift, so no single tempo fits. Beat This!
finds every beat and downbeat, stored in `timing.detected.beat_map`
(`beats_s`, `downbeats_s`, `positions` = beat numbers, first downbeat on a bar
line). The export then works as follows:
- Live tempo = the median local tempo.
- Every audio clip is placed at bar 1 with Warp on and one warp marker per
  beat. Each marker's `sample_time` uses that file's own sync offset.
- MIDI notes are placed with `to_beats()` (piecewise linear between beats).
  Their microtiming relative to the beat is kept; nothing is quantised.

The warp markers use the documented `Clip.add_warp_marker`. Audio files are
never altered. A user timing correction switches the export back to
constant mode.

## MIDI export
`mrs/export.py`. MIDI time = audio time + `pad_s`, where `pad_s` puts the
first downbeat on a bar line. `export.json` records the tempo, `pad_s` and the
start time for each audio file, which the Live builder and manual import both
use. There is no quantising.

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
