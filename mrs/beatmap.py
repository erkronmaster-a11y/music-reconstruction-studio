"""Beat map: every beat and downbeat of a song whose tempo is not steady.

Why: early AI-generated songs drift — on the owner's first song no single tempo
fits (beats wander ±100 ms around any straight grid). For easy editing the
song is put on a straight grid in Live by warping the audio at every detected
beat, and MIDI notes are placed by the same map. The audio files are never
altered; warping happens at playback in Live.

Detector: Beat This! (Foscarin, Schlüter, Widmer, ISMIR 2024), "final0"
checkpoint, no DBN post-processing (keeps tempo changes). On a test song with
±3 % tempo wobble: median beat error 6 ms, 40/40 downbeats; librosa 22 ms.
Fallback when it is not installed: librosa's tracker, labelled as such.

Positions: beat number b (float, 0 = start of Live bar 1). The first detected
downbeat sits on a bar line; pickup beats come before it.
"""
from __future__ import annotations

import numpy as np


def detect(path: str) -> dict:
    try:
        from beat_this.inference import File2Beats
        import importlib.metadata as md
        beats, downs = File2Beats(checkpoint_path="final0", device="cpu", dbn=False)(str(path))
        method = f"beat_this {md.version('beat-this')} final0 (no DBN)"
    except ImportError:
        import librosa
        from . import audio
        y, sr = audio.load(path, sr=22050)
        _, bf = librosa.beat.beat_track(y=y, sr=sr, hop_length=256)
        beats = librosa.frames_to_time(bf, sr=sr, hop_length=256)
        downs = beats[::4]
        method = f"librosa {librosa.__version__} beat_track (FALLBACK — beat_this not installed; downbeats assumed every 4)"
    beats = np.asarray(beats, float)
    downs = np.asarray(downs, float)
    return build(beats, downs, method)


def build(beats: np.ndarray, downs: np.ndarray, method: str, beats_per_bar: int = 4) -> dict:
    beats = np.unique(np.round(beats, 4))
    if len(beats) < 8:
        return {"method": method, "beats_s": beats.tolist(), "downbeats_s": [], "positions": [],
                "note": "too few beats for a beat map"}
    # snap each downbeat to its nearest beat index
    down_idx = sorted({int(np.argmin(np.abs(beats - d))) for d in downs})
    first = down_idx[0] if down_idx else 0
    # the first downbeat goes on the first bar line that leaves room for the pickup
    first_pos = int(np.ceil(first / beats_per_bar)) * beats_per_bar
    positions = (np.arange(len(beats)) - first + first_pos).astype(float)
    # bars whose length is not beats_per_bar (downbeat-to-downbeat beat counts)
    irregular = []
    for a, b in zip(down_idx, down_idx[1:]):
        if b - a != beats_per_bar:
            irregular.append({"at_s": round(float(beats[a]), 3), "beats": b - a})
    ibi = np.diff(beats)
    local_bpm = 60.0 / ibi
    return {"method": method, "beats_s": [round(float(b), 4) for b in beats],
            "downbeats_s": [round(float(beats[i]), 4) for i in down_idx],
            "positions": positions.tolist(), "beats_per_bar": beats_per_bar,
            "live_tempo_bpm": round(float(np.median(local_bpm)), 2),
            "tempo_range_bpm": [round(float(np.percentile(local_bpm, 5)), 1), round(float(np.percentile(local_bpm, 95)), 1)],
            "irregular_bars": irregular}


def to_beats(bm: dict, t_s: np.ndarray | float) -> np.ndarray:
    """Seconds (mix timeline) → beat number, piecewise linear between detected
    beats, extrapolated with the nearest local tempo outside them."""
    b = np.asarray(bm["beats_s"]); p = np.asarray(bm["positions"])
    t = np.atleast_1d(np.asarray(t_s, float))
    out = np.interp(t, b, p)
    lo, hi = t < b[0], t > b[-1]
    out[lo] = p[0] - (b[0] - t[lo]) / (b[1] - b[0])
    out[hi] = p[-1] + (t[hi] - b[-1]) / (b[-1] - b[-2])
    return out


def warp_markers(bm: dict, offset_s: float = 0.0, length_s: float | None = None) -> list[dict]:
    """Live warp markers for one audio file: sample_time is seconds in THAT
    file (mix time + the file's sync offset), beat_time the grid position."""
    out = []
    for t, p in zip(bm["beats_s"], bm["positions"]):
        st = t + offset_s
        if st < 0 or (length_s is not None and st > length_s):
            continue
        out.append({"sample_time": round(st, 5), "beat_time": float(p)})
    return out
