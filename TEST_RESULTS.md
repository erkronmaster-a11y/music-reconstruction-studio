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

**Not yet verified on a real song or on the Mac.**

## Sprint 0 — unit tests
`pytest tests/` → 3 passed. Covers the .amxd container structure, that the
bridge script is present, and the test tone.
