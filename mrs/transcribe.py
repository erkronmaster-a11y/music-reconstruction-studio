"""Audio → notes. Each method returns a *raw* layer; nothing here edits notes
to sound better.

Method per role (chosen from the Sprint 0 probe, see TEST_RESULTS.md):
  bass   → pYIN pitch tracking + onset splitting (monophonic; F1 0.95 vs 0.50 for Basic Pitch on low bass)
  melody → Basic Pitch (polyphonic; F1 1.00 on melody) — keeps chords if the stem has them
  other  → Basic Pitch

Note format (seconds on the MIX timeline — stem sync offsets are already removed):
  {"start_s", "end_s", "pitch" (MIDI int), "velocity" (1-127),
   "confidence" (0-1, method-specific, see `confidence_meaning`),
   "flags" (optional): e.g. ["possible_octave_ghost"] — annotations, never deletions}
"""
from __future__ import annotations

import numpy as np

from . import audio

SR = 22050
HOP = 256
RANGES = {"bass": (28, 64), "melody": (48, 96), "other": (36, 96), "drums": (35, 81)}   # MIDI note ranges searched


def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def pyin_notes(y: np.ndarray, sr: int, lo: int, hi: int, min_dur: float = 0.05) -> list[dict]:
    import librosa
    f0, voiced, prob = librosa.pyin(y, fmin=_hz(lo - 1), fmax=_hz(hi + 1), sr=sr,
                                    frame_length=2048, hop_length=HOP)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=HOP)[0]
    onsets = set(librosa.onset.onset_detect(y=y, sr=sr, hop_length=HOP, backtrack=True).tolist())
    midi = np.where(voiced, np.round(librosa.hz_to_midi(np.nan_to_num(f0, nan=1.0))), -1).astype(int)
    peak = float(rms.max()) or 1.0
    notes, cur, start = [], -1, 0
    for i, m in enumerate(list(midi) + [-1]):
        if m != cur or (i in onsets and cur != -1):
            if cur != -1 and (i - start) * HOP / sr >= min_dur:
                seg = slice(start, i)
                loud = float(np.sqrt(np.mean(rms[seg] ** 2)) / peak)
                notes.append({"start_s": round(start * HOP / sr, 4), "end_s": round(i * HOP / sr, 4),
                              "pitch": int(cur), "velocity": int(np.clip(30 + 97 * loud ** 0.5, 1, 127)),
                              "confidence": round(float(np.mean(prob[seg])), 3)})
            cur, start = m, i
    return _merge_slivers(notes)


def _merge_slivers(notes: list[dict], sliver: float = 0.1, gap: float = 0.03) -> list[dict]:
    """Part of the segmentation, not a clean-up of results: an onset inside a
    held note can cut off a sliver (< 100 ms) of the same pitch with no gap.
    Such a sliver is joined to its neighbour. Repeated real notes of the same
    pitch are kept when both are longer than 100 ms or separated by a gap."""
    out: list[dict] = []
    for n in notes:
        prev = out[-1] if out else None
        if (prev and prev["pitch"] == n["pitch"] and n["start_s"] - prev["end_s"] <= gap
                and min(n["end_s"] - n["start_s"], prev["end_s"] - prev["start_s"]) < sliver):
            prev["end_s"] = n["end_s"]
            prev["confidence"] = round(min(prev["confidence"], n["confidence"]), 3)
            continue
        out.append(dict(n))
    return out


def basic_pitch_notes(path: str, lo: int, hi: int) -> tuple[list[dict], str]:
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict
    import basic_pitch
    _, _, events = predict(str(path), ICASSP_2022_MODEL_PATH, minimum_frequency=_hz(lo), maximum_frequency=_hz(hi),
                           multiple_pitch_bends=False)
    notes = [{"start_s": round(float(s), 4), "end_s": round(float(e), 4), "pitch": int(p),
              "velocity": int(np.clip(round(127 * float(a)), 1, 127)), "confidence": round(float(a), 3)}
             for s, e, p, a, *_ in events]
    notes.sort(key=lambda n: (n["start_s"], n["pitch"]))
    return notes, f"basic-pitch {getattr(basic_pitch, '__version__', '0.4.0')} ({ICASSP_2022_MODEL_PATH.name})"


def flag_octave_ghosts(notes: list[dict], onset_tol: float = 0.04, ratio: float = 1.5) -> int:
    """Mark (never delete) notes that look like a strong 2nd harmonic heard as a
    note: same onset (±40 ms) as a note exactly 12 semitones lower that is at
    least 1.5× louder. Real octave doublings exist, so this is only a flag;
    the raw layer keeps every note and the raw MIDI export includes them."""
    flagged = 0
    for n in notes:
        for low in notes:
            if (low["pitch"] == n["pitch"] - 12 and abs(low["start_s"] - n["start_s"]) <= onset_tol
                    and low["confidence"] >= ratio * n["confidence"]):
                n["flags"] = sorted(set(n.get("flags", [])) | {"possible_octave_ghost"})
                flagged += 1
                break
    return flagged


def transcribe_source(src: dict, role: str) -> dict:
    """Returns a raw layer for one source file."""
    import librosa
    lo, hi = RANGES.get(role, RANGES["other"])
    offset = (src.get("sync") or {}).get("offset_s", 0.0)
    if role == "drums":
        from . import drums
        y, sr = audio.load(src["path"], sr=drums.SR)
        notes = drums.to_notes(drums.detect(y, sr))
        method = "mrs band-onset drums v1 (SuperFlux per band; kick/snare/closed+open hat/unclassified)"
        meaning = "onset strength above the adaptive threshold, 0-1 (hat under a snare ×0.7, unclassified ×0.6)"
    elif role == "bass":
        y, sr = audio.load(src["path"], sr=SR)
        notes = pyin_notes(y, sr, lo, hi)
        method = f"librosa {librosa.__version__} pyin + onset split"
        meaning = "mean pYIN voicing probability over the note"
    else:
        notes, method = basic_pitch_notes(src["path"], lo, hi)
        meaning = "Basic Pitch note amplitude (model activation), not a probability of correctness"
        flag_octave_ghosts(notes)
    if offset:
        for n in notes:  # stem time → mix time
            n["start_s"] = round(n["start_s"] - offset, 4)
            n["end_s"] = round(n["end_s"] - offset, 4)
        notes = [n for n in notes if n["end_s"] > 0]
    return {"method": method, "pitch_range": [lo, hi], "source_id": src["id"], "sync_offset_applied_s": offset,
            "confidence_meaning": meaning, "notes": notes}
