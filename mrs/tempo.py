"""Global tempo, beats and first downbeat.

Detection: librosa's dynamic-programming beat tracker on the full mix.
Downbeat: among the 4 possible bar phases, the one whose beats carry the most
low-frequency (kick/bass) onset energy plus the biggest harmonic (chroma) change. This is a heuristic — it assumes 4/4
and that bars start on a low hit — so it reports its confidence, and the user
can correct both tempo and first downbeat (see manifest.Timing).
"""
from __future__ import annotations

import numpy as np

SR = 22050
HOP = 256


def detect(y: np.ndarray, sr: int = SR, beats_per_bar: int = 4) -> dict:
    import librosa
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP, aggregate=np.median)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=HOP, units="frames")
    tempo = float(np.atleast_1d(tempo)[0])
    beats = librosa.frames_to_time(beat_frames, sr=sr, hop_length=HOP)
    out = {"method": f"librosa {librosa.__version__} beat_track + downbeat phase (low-band onsets + chroma change)",
           "tempo_bpm": round(tempo, 3), "beats_s": [round(float(b), 4) for b in beats],
           "beats_per_bar": beats_per_bar, "first_downbeat_s": None, "downbeat_confidence": 0.0,
           "tempo_stability": None}
    if len(beats) < beats_per_bar * 2:
        out["note"] = "too few beats detected"
        return out
    ibi = np.diff(beats)
    # Spread of beat intervals relative to their median: ~0 for a steady grid.
    out["tempo_stability"] = round(float(np.std(ibi) / np.median(ibi)), 4)
    # Tempo from the median interval is more robust than the tracker's prior-weighted estimate.
    out["tempo_bpm"] = round(60.0 / float(np.median(ibi)), 3)

    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    low = S[freqs < 150].sum(axis=0)
    low_onset = np.maximum(0, np.diff(low, prepend=low[:1]))
    frames = np.clip(beat_frames, 0, len(low_onset) - 1)
    # Max within ±2 frames, so a hit a few ms off the tracked beat still counts.
    strength = np.array([low_onset[max(0, f - 2):f + 3].max() for f in frames])
    # Second cue: harmony tends to change at the bar line. Chroma flux between
    # the beat before and the beat after each beat position.
    C = librosa.feature.chroma_stft(S=S ** 2, sr=sr)
    seg = np.split(C, np.clip(frames, 1, C.shape[1] - 1), axis=1)
    beat_chroma = np.array([x.mean(axis=1) if x.shape[1] else np.zeros(12) for x in seg])  # chroma before each beat, then after the last
    after, before = beat_chroma[1:], beat_chroma[:-1]
    flux = np.linalg.norm(after / (after.sum(1, keepdims=True) + 1e-9) - before / (before.sum(1, keepdims=True) + 1e-9), axis=1)

    def z(v):
        return (v - v.mean()) / (v.std() + 1e-9)
    combined = z(strength) + z(flux[: len(strength)])
    scores = np.array([combined[p::beats_per_bar].mean() for p in range(beats_per_bar)])
    scores = scores - scores.min()  # non-negative, so the confidence ratio below means something
    best = int(np.argmax(scores))
    srt = np.sort(scores)
    # The tracker often locks on a bar or two into the song. Step back whole bars
    # while that stays at or after the first sound, so bar 1 is the music's first bar.
    first = float(beats[best])
    bar_s = beats_per_bar * float(np.median(ibi))
    loud = np.nonzero(env > 0.1 * env.max())[0]
    music_start = float(librosa.frames_to_time(loud[0], sr=sr, hop_length=HOP)) if len(loud) else 0.0
    while first - bar_s >= music_start - 0.05:
        first -= bar_s
    out["first_downbeat_s"] = round(max(0.0, first), 4)
    out["downbeat_confidence"] = round(float((srt[-1] - srt[-2]) / (srt[-1] + 1e-12)), 3)
    return out


def grid(tempo_bpm: float, first_downbeat_s: float, duration_s: float, beats_per_bar: int = 4) -> list[dict]:
    """A constant-tempo grid through the first downbeat, covering the whole file
    (beats before the downbeat get negative bar numbers: a pickup)."""
    period = 60.0 / tempo_bpm
    k0 = -int(np.floor(first_downbeat_s / period))
    out = []
    k = k0
    while True:
        t = first_downbeat_s + k * period
        if t > duration_s:
            break
        bar, beat = divmod(k, beats_per_bar)
        out.append({"time_s": round(t, 5), "bar": bar + 1, "beat": beat + 1})
        k += 1
    return out
