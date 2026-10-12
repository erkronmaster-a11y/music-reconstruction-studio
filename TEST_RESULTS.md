# Test results

## Sprint 0 — transcription probe (2026-10-12, Linux x86_64, Python 3.11)

**Setup:** known monophonic parts, with ±12 ms human microtiming, rendered by an
additive synth and scored with `mir_eval` (onset tolerance 50 ms, offset ratio
0.2). This is synthetic audio, so real mixes **will score lower**. The numbers
rank the methods; they don't predict accuracy on your songs.
Raw data: `reports/sprint0/transcription-probe.json`.

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

## Sprint 0 — Ableton Live API test
*Pending: Erick runs SETUP_MACOS.md steps 2–3.*

## Sprint 0 — unit tests
`pytest tests/` → 3 passed. Covers the .amxd container structure, that the
bridge script is present, and the test tone.
