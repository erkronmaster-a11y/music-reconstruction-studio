"""Synthetic test song with exact ground truth (tempo, downbeat, notes, offsets).

Used by tests now and as transcription ground truth in Sprint 1b. Rendered,
never guessed: every number in `truth` is what produced the audio.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100


def _tone(f0, dur, sr, harmonics=(1, .5, .3, .2), decay=3.0):
    t = np.arange(int(dur * sr)) / sr
    env = np.minimum(1, t / 0.004) * np.exp(-t * decay) * np.minimum(1, (len(t) - np.arange(len(t))) / (0.01 * sr))
    return env * sum(a * np.sin(2 * np.pi * f0 * (k + 1) * t) for k, a in enumerate(harmonics) if f0 * (k + 1) < sr / 2)


def _add(buf, sig, t, sr):
    i = int(round(t * sr))
    if i >= len(buf):
        return
    sig = sig[: len(buf) - i]
    buf[i:i + len(sig)] += sig


def make(out: str | Path, bpm=123.0, first_downbeat=0.37, bars=16, stem_offsets=None, seed=3,
         formats=("wav",)) -> dict:
    """Writes mix + stems into `out`; returns ground truth (also saved as truth.json)."""
    rng = np.random.default_rng(seed)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stem_offsets = stem_offsets or {}
    beat = 60.0 / bpm
    dur = first_downbeat + bars * 4 * beat + 1.0
    n = int(dur * SR)
    parts = {k: np.zeros(n) for k in ("drums", "bass", "melody", "vocals")}
    truth = {"bpm": bpm, "first_downbeat_s": first_downbeat, "beats_per_bar": 4, "bars": bars,
             "sample_rate": SR, "stem_offsets_s": stem_offsets, "notes": {"bass": [], "melody": []}}
    kick = lambda: _tone(55, 0.25, SR, (1,), decay=18) * 1.6
    snare = lambda: rng.normal(0, 0.4, int(0.15 * SR)) * np.exp(-np.arange(int(0.15 * SR)) / SR * 30)
    hat = lambda: rng.normal(0, 0.12, int(0.05 * SR)) * np.exp(-np.arange(int(0.05 * SR)) / SR * 90)
    roots = [40, 40, 43, 45, 38, 38, 43, 47]
    scale = [0, 2, 4, 7, 9, 12]
    for bar in range(bars):
        b0 = first_downbeat + bar * 4 * beat
        for k in range(4):
            t = b0 + k * beat
            _add(parts["drums"], kick() if k in (0, 2) else snare(), t, SR)
        for k in range(8):
            _add(parts["drums"], hat(), b0 + k * beat / 2, SR)
        root = roots[bar % len(roots)]
        for k, (st, ln) in enumerate([(0, 1.5), (2, 1.0), (3, 0.75)]):
            p = root if k == 0 else root + (7 if k == 1 else 12)
            _add(parts["bass"], _tone(440 * 2 ** ((p - 69) / 12), ln * beat, SR, decay=2) * 0.8, b0 + st * beat, SR)
            truth["notes"]["bass"].append([round(b0 + st * beat, 5), round(b0 + (st + ln) * beat, 5), p])
        for k in range(4):
            p = 72 + scale[rng.integers(len(scale))] - (12 if bar % 2 else 0)
            st = k + rng.choice([0, 0.5])
            _add(parts["melody"], _tone(440 * 2 ** ((p - 69) / 12), 0.45 * beat, SR) * 0.35, b0 + st * beat, SR)
            truth["notes"]["melody"].append([round(b0 + st * beat, 5), round(b0 + st * beat + 0.45 * beat, 5), p])
        if bar % 4 in (1, 2):  # vocals only in some bars, so the stem has silence
            _add(parts["vocals"], _tone(220, 3.5 * beat, SR, (1, .8, .6, .5, .4, .3), decay=0.5) * 0.3, b0, SR)
    mix = sum(parts.values())
    peak = np.abs(mix).max() * 1.1
    files = {}
    for fmt in formats:
        ext = {"wav": "wav", "aiff": "aiff", "flac": "flac", "mp3": "mp3"}[fmt]
        sf.write(out / f"Test Song MIX.{ext}", np.stack([mix, mix], 1) / peak, SR)
        files[f"mix.{fmt}"] = f"Test Song MIX.{ext}"
    for name, y in parts.items():
        off = stem_offsets.get(name, 0.0)
        if off > 0:
            y = np.concatenate([np.zeros(int(round(off * SR))), y])[:n]
        elif off < 0:
            y = np.concatenate([y[int(round(-off * SR)):], np.zeros(int(round(-off * SR)))])
        sf.write(out / f"Test Song {name}.wav", np.stack([y, y], 1) / peak, SR)
    (out / "truth.json").write_text(json.dumps(truth, indent=1))
    return truth
