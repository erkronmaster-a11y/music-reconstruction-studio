# Test results

## Sprint 0 — transcription probe (2026-10-12, Linux x86_64, Python 3.11)

**Setup:** known monophonic parts, with ±12 ms human microtiming, rendered by an
additive synth and scored with `mir_eval` (onset tolerance 50 ms, offset ratio
0.2). This is synthetic audio, so real mixes **will score lower**. The numbers
rank the methods; they don't predict accuracy on your songs.
Raw data: `reports/sprint0/transcription-probe-linux.json`.

| Case | Method | Precision | Recall | Onset F1 | Onset+offset F1 | Mean onset error | Time |
|---|---|---|---|---|---|---|---|
| Bass E1–E3 (40 notes) | Basic Pitch 0.4.0 | 0.39 | 0.70 | **0.50** | 0.39 | 21 ms | 4.1 s |
| Bass E1–E3 (40 notes) | pYIN + onsets | 0.91 | 1.00 | **0.95** | 0.95 | 4.5 ms | 3.0 s |
| Melody C4–C6 (48 notes) | Basic Pitch 0.4.0 | 1.00 | 1.00 | **1.00** | 0.88 | 5.3 ms | 1.6 s |
| Melody C4–C6 (48 notes) | pYIN + onsets | 0.51 | 1.00 | **0.68** | 0.68 | 4.0 ms | 3.3 s |

Peak memory: about 0.9 GB (TensorFlow included).

**Takeaways**
- Basic Pitch works and is very good on melody. It is poor on low bass: it
  produced 72 notes for 40, mostly octave and harmonic errors.
- pYIN is reliable on bass. On melody it splits notes too often (94 for 48);
  the segmentation needs tuning in Sprint 1.
- Plan: use the best method per instrument, and keep both outputs as separate
  raw layers.

**Compatibility issues found and fixed (pinned in `requirements.txt`)**
1. NumPy 2 crashes TensorFlow 2.14 on import → `numpy==1.26.4`.
2. `resampy` needs `pkg_resources`, which setuptools 81+ no longer ships →
   `setuptools<81`.
3. On macOS, Basic Pitch 0.4.0 uses CoreML. Its TF dependency on Darwin applies
   only from Python 3.12 → use **Python 3.11** on the Mac. *Not yet verified on
   the Mac.*

## Sprint 0 — Ableton Live API test ✅ (2026-10-12)
**Mac:** M1 Pro, 16 GB, macOS 13.6.1 · **Live 12.0.15 Suite** · bundled Max 8.6.2 ·
raw data: `reports/sprint0/live-create.json`, `live-verify.json`, `mac-env.txt`.

| Operation | Result |
|---|---|
| Create MIDI / audio track, set name and colour | ✅ |
| Set tempo (117.5) | ✅, and it survives save/reopen |
| `Track.create_midi_clip` (arrangement) | ❌ **not available on 12.0.15**: no clip is created and no error is raised |
| Fallback: Session `create_clip` → `add_new_notes` → `duplicate_clip_to_arrangement` → delete the Session clip | ✅ clip at beat 4, length 4 |
| `add_new_notes` with a JS object | ✅ |
| 4 notes read back, including the off-grid note at 2.037 beats | ✅ 2.036999979 (float32; error ≈ 2×10⁻⁸ beats, inaudible) |
| `Track.create_audio_clip` (arrangement, WAV path) | ✅ works on 12.0.15 |
| Save → quit → reopen → read back | ✅ track, clip position, all 4 notes, audio clip and tempo |
| Save the Set from the API | ⛔ not in the LOM; the user presses ⌘S |

**Bugs found on the way (fixed):**
- `File.isopen` was true while nothing was written. Saves are now read back to confirm them.
- The device path was not `<repo>/live/<file>`. The repo is now found by
  cutting the path at the `/live` folder.

## Sprint 1a — import, sync, timing (2026-10-12, Linux, synthetic ground truth)
`pytest tests/` → **17 passed**. The test song is rendered at 123 BPM, first
downbeat 0.37 s, with drums, bass, melody and vocals stems.

| Check | Result |
|---|---|
| Decode WAV / AIFF / FLAC / MP3 (libsndfile 1.2.2) | ✅ all four |
| Stem roles from file names (the song title appears in every name) | ✅ after a fix: "Song" in a title was read as "mix" |
| Bass stem padded by 20 ms → measured offset | ✅ 20.0 ms (tolerance 1 ms); the other stems read 0.0 ms |
| Tempo | ✅ within 1% (123.05 against 123) |
| Beats on the true grid | ✅ median error < 30 ms |
| First downbeat | ✅ within 30 ms. ⚠️ Confidence is low (0.07) because the kick hits on both 1 and 3, and the tool says so |
| Corrections never change the detected values; save → load → clear works | ✅ |
| NI `.stem.mp4` (5 AAC streams + `stem` metadata) → WAVs → analysis | ✅ stems aligned 0.0 ms; names read from the metadata; default order used when the metadata is missing |
| 64 s song, full analysis (cloud CPU) | 7.4 s |

**Fixed along the way:** stem sync originally compared onset envelopes. On
rhythmic stems it locked one beat off (a 0.5 s error), so it now
cross-correlates the waveforms. The beat tracker also started counting a bar
late; the first downbeat now steps back to the first bar of music.

### On the Mac (2026-10-12, M1 Pro, macOS 13.6.1, Python 3.11.16, ffmpeg 8.1.1)
- `pytest`: **18 passed** in 90 s.
- Basic Pitch 0.4.0 runs through **CoreML** (coremltools 9.0). The probe
  scores match Linux exactly (bass F1 0.50, melody F1 1.00); peak memory is
  about 270 MB.
- Install fixes on the way:
  - Homebrew can't install `uv` on macOS 13 ("Tier 3"), so the install now
    uses `python3.11 -m venv` + pip.
  - The first pip run failed silently; pip errors now go into the report.
  - `onnxruntime` is Linux-only now.
- Traktor 4 keeps **184 `.stem.mp4` files (9.4 GB)** in `~/Music/Traktor/Stems/`.
  They carry **no title tags**, and **0 of 184 codes** appear in
  `collection.nml`. Titles therefore come from a **unique track-length match**
  against the NML (`PLAYTIME_FLOAT`). Ambiguous matches are not guessed.

**Not yet verified on a real song.**

## Sprint 1a fix — click drifted on a real song (2026-10-12)
**Report from the Mac:** the click started on the one, then drifted. The song
measured 132.512 BPM with a 10% beat-spacing spread.

**Cause:** the tempo came from the median beat interval of librosa's tracker.
Its beats are quantised to 11.6 ms frames and drift on their own. On test
songs it was off by up to 1.2 BPM (129.2 against a true 128). At 132 BPM, a
0.5 BPM error is about 0.4 s of drift over 2.5 minutes.

**Fix:** an onset-comb fit. Every tempo within ±3% of the tracker's (coarse
0.05, then fine 0.001 BPM) is scored against the whole onset curve, and the
best one wins.

| True BPM | Old | New |
|---|---|---|
| 132.0 | 132.512 | 132.007 |
| 128.0 | 129.199 | 128.007 |
| 97.3 | 97.509 | 97.306 |

The test now requires < 20 ms drift over 2.5 minutes. A `click-follow.wav`
(clicks on the tracker's own beats) and a grid-gap figure (early against late)
now show when a song's tempo **really** changes, which a single tempo can't
follow (a tempo map is on the roadmap).

## Sprint 1c — beat map for drifting songs (2026-10-12, Linux)
**From the Mac:** on the owner's song the beats wander about ±100 ms around
**any** constant grid, early and late. The tempo isn't steady, so one BPM
can't fit.

On a test song with a ±3% tempo wobble (128 BPM base):

| Detector | Beat error (median / 95%) | Downbeats |
|---|---|---|
| librosa beat_track | 22.3 / 28.9 ms | — |
| **Beat This! 1.1.0 (final0, no DBN)** | **6.1 / 19.2 ms** | **40 / 40** within 70 ms |

Beat This! takes about 8 s per 80 s of audio on CPU.

- **Tests:** `pytest` → **31 passed**. In the drifting-song test, bass notes
  land on whole beats after mapping (median off-grid < 0.04 beat). Each stem's
  sync offset is carried into its own warp markers.
- **Not yet checked in Live:** that warp markers placed through the LOM play
  the song in time (Sprint 3 / next Mac test).

## Sprint 1b — bass + melody → MIDI (2026-10-12, Linux, synthetic ground truth)
`pytest tests/` → **28 passed**. Scored with `mir_eval` (onset ±50 ms, pitch exact).

| Part | Method | Precision | Recall | F1 |
|---|---|---|---|---|
| Bass stem (padded 15 ms) | pYIN + onset split + sliver merge | 1.00 | 1.00 | **1.00** |
| Melody stem | Basic Pitch, clean view | 1.00 | 1.00 | **1.00** |
| Melody stem | Basic Pitch, raw view | 0.55 | 1.00 | 0.71 |

**What changed along the way**
- **Raw melody:** Basic Pitch hears a strong 2nd harmonic as a second note one
  octave up. Those notes are now **flagged** `possible_octave_ghost`, never
  deleted. The default MIDI leaves them out; `midi/raw/` keeps them, because
  real octave doublings exist.
- **Bass:** onsets inside a held note cut off 60–80 ms slivers of the same
  pitch (precision 0.80). The segmentation now joins a sliver to its neighbour.
- **Stem offset:** a 15 ms stem offset is removed (median error < 12 ms).
- **MIDI export:** the tempo is correct, the first downbeat lands exactly on a
  bar line (pad recorded in `export.json`), notes are shifted by exactly the
  pad and are **not quantised**.

**Full-length song (235.5 s, cloud CPU):** analyse 22.6 s · transcribe 51.3 s
· export + review 16.0 s · peak memory ≈ 1.1 GB. Bass 360/360 notes; melody
488 clean against 480 true (chroma agreement 0.995 / 0.97 — a listening aid,
not an accuracy figure).

**These are synthetic tones.** Real songs will score lower, and real songs
have no ground truth, so they are judged by listening (review/ A/B files),
never by an invented accuracy number.

## Sprint 0 — unit tests
`pytest tests/` → 3 passed. Covers the .amxd container structure, that the
bridge script is present, and the test tone.
