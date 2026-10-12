# Roadmap

Usage estimates are a rough share of the plan's usage ceiling. Any sprint likely
to go over **10%** is split up, or confirmed with Erick before it starts.

| Sprint | Contents | Estimate | State |
|---|---|---|---|
| 0 | Mac check, Live API test (create → save → reopen → verify), Basic Pitch vs alternative | 5–8% | ✅ done |
| 1a | Load WAV/AIFF/FLAC/MP3 + **Traktor/NI `.stem.mp4`**, inspect, sync stems, tempo + beats + first downbeat (user-correctable), click check, manifest v1 | 8–10% (actual ≈ 12%) | ✅ Mac install verified; real-song click check pending |
| 1b | Bass (pYIN) + melody (Basic Pitch) transcription, octave-ghost flags, MIDI export aligned to bar lines, A/B review | 10–12% | 🟡 built + tested in cloud; real song pending |
| 1c | Beat map (Beat This!): every beat + downbeat; Live tempo constant, audio warped at each beat, MIDI placed by the map | 8–10% | ✅ real song: beat-map click stays tight by ear; Live warping verified in Sprint 3 |
| GUI v1 | **Loomback**: local web app in SMV Studio's design language — run steps, beat/bar timeline, piano roll, A/B mixer (stems ↔ MIDI ↔ click), timing correction | ≈9% | 🟡 built + browser-tested in cloud; Mac pending |
| 2 | Drums: kick / snare / closed hat / open hat / unclassified, GM mapping, groove kept | 10–14% | — |
| 3 | Live arrangement builder + fallback export package | 10–14% | — |
| 4a | Editor: pitch / length / onset / delete / add, beat grid | 8–10% | — |
| 4b | A/B playback, selective reanalysis | 8–10% | — |

## Early direction from the Sprint 0 probe
- On synthetic tones, Basic Pitch is strong on **melody** but weak on **low bass**.
  pYIN is the reverse. Sprint 1 therefore plans: pYIN-led bass, Basic Pitch-led
  melody, with both outputs kept and compared.

## Known weak spots to revisit
- **Downbeat:** a heuristic (low-band onsets + chroma change). Its confidence is low
  when the kick lands on both 1 and 3. Candidate upgrade: the `beat_this` model
  (CPJKU, 2024) for beats and downbeats. Until then, the click check plus a
  manual correction covers it.
- **Tempo:** a single global value. Songs with tempo changes need a tempo map
  (later).

## Not now
Elaborate UI, preset matching, mastering, licensing.
