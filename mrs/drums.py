"""Drums stem → drum hits (Sprint 2).

Method: band-wise onset detection on the drums stem (DSP, no trained model).
Each kit piece lives mostly in its own frequency band, so each band gets its
own onset curve. A kick and a hi-hat on the same instant are both found.

  kick        30–150 Hz onsets
  snare       1.2–5 kHz noise onsets with a 150–400 Hz body
  closed hat  > 7 kHz onsets that die away fast
  open hat    > 7 kHz onsets that ring (> 150 ms above -20 dB)
  unclassified  any full-band onset none of the above explains

Known limits (heuristics, so every hit carries a confidence and a class):
  - a hat played on the same instant as a snare is decided by how much
    > 7 kHz energy the hit adds compared with its 1.2–5 kHz energy;
  - toms and cymbals have no class of their own yet → kick/snare/unclassified.

Times are on the drums stem's timeline; the caller removes the sync offset.
"""
from __future__ import annotations

import numpy as np

SR = 44100
HOP = 128          # 2.9 ms
N_FFT = 1024

# General MIDI drum notes (what Ableton's Drum Rack kits expect)
GM = {"kick": 36, "snare": 38, "closed_hat": 42, "open_hat": 46, "unclassified": 39}
GM_NAMES = {36: "Kick (C1)", 38: "Snare (D1)", 42: "Closed hi-hat (F#1)", 46: "Open hi-hat (A#1)",
            39: "Unclassified percussion (D#1, hand clap slot)"}


def _band(S, freqs, lo, hi):
    return S[(freqs >= lo) & (freqs < hi)].sum(axis=0)


def _flux(Sb, lag: int = 3):
    """SuperFlux-style onset curve inside one band (Böck & Widmer 2013):
    per-bin log energy compared with a frequency-max-filtered copy from `lag`
    frames earlier. Per bin, so a new hit shows while another sound in the band
    rings (hat inside a snare tail); the max filter and lag stop the random
    flicker of noise tails from looking like hits."""
    from scipy.ndimage import maximum_filter1d
    L = np.log1p(100 * Sb / (Sb.max() + 1e-12))
    ref = maximum_filter1d(L, size=3, axis=0)
    d = np.zeros_like(L)
    d[:, lag:] = L[:, lag:] - ref[:, :-lag]
    return np.maximum(0.0, d).sum(axis=0)


def _peaks(f, min_gap_s=0.05, k=1.5):
    """Local maxima above an adaptive threshold (moving median + k·MAD)."""
    import librosa
    w = int(0.4 * SR / HOP)
    med = np.convolve(f, np.ones(w) / w, mode="same")
    thr = med + k * np.median(np.abs(f - np.median(f))) + 0.02 * f.max()
    p = librosa.util.peak_pick(f, pre_max=3, post_max=3, pre_avg=10, post_avg=10, delta=0.0, wait=int(min_gap_s * SR / HOP))
    p = np.array([i for i in p if f[i] > thr[i]], dtype=int)
    strength = (f[p] - thr[p]) / (f.max() - thr[p] + 1e-9) if len(p) else np.array([])
    return p, np.clip(strength, 0, 1)


def detect(y: np.ndarray, sr: int = SR) -> list[dict]:
    import librosa
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    low, body, mid, high = (_band(S, freqs, 30, 150), _band(S, freqs, 150, 400),
                            _band(S, freqs, 1200, 5000), _band(S, freqs, 7000, sr / 2))
    lowmid = _band(S, freqs, 400, 1200)
    full = S.sum(axis=0)
    rows = lambda lo, hi: S[(freqs >= lo) & (freqs < hi)]
    t = lambda i: float(librosa.frames_to_time(i, sr=sr, hop_length=HOP))
    win = int(0.03 * sr / HOP)  # 30 ms look-ahead for the hit's spectrum

    hits = []

    def add(i, cls, conf, strength):
        hits.append({"time_s": round(t(i), 4), "class": cls, "pitch": GM[cls], "confidence": round(float(conf), 3),
                     "_strength": float(strength)})

    # kick: a low-band onset that is loud for this song's low end — the log
    # flux also jumps when a snare's broadband noise leaks a little low energy
    p, c = _peaks(_flux(rows(30, 150)))
    if len(p):
        lv = np.array([low[i:i + win].max() for i in p])
        ref = np.percentile(lv, 90)
        for i, ci, v in zip(p, c, lv):
            if v > 0.2 * ref:
                add(i, "kick", ci, v)

    # snare: mid-band noise onset with some body, and not just a hat (hat energy is mostly > 7 kHz)
    p, c = _peaks(_flux(rows(1200, 5000)))
    snare_frames = []
    for i, ci in zip(p, c):
        m, h, b = mid[i:i + win].sum(), high[i:i + win].sum(), body[i:i + win].sum()
        lm = lowmid[i:i + win].sum()
        # noise-like snare: its 1.2–5 kHz energy dominates the 0.4–1.2 kHz range
        # (a tonal click like a woodblock does not) and it is not mostly hat
        if m > 0.5 * h and b > 0.02 * m and m > 0.6 * lm:
            add(i, "snare", ci, m)
            snare_frames.append(i)
    snare_frames = np.array(snare_frames)

    # hats
    p, c = _peaks(_flux(rows(7000, sr / 2)), min_gap_s=0.04)
    ring_until, ring_peak = -1, 0.0
    for i, ci in zip(p, c):
        # inside a still-ringing open hat, only a clearly louder hit is new
        if i < ring_until and high[i:i + win].max() < 1.2 * high[i - 1] :
            continue
        m, h = mid[i:i + win].sum(), high[i:i + win].sum()
        if len(snare_frames) and np.min(np.abs(snare_frames - i)) <= win:
            if h < 0.35 * m:         # mostly snare noise: no hat on top
                continue
            ci *= 0.7                # hat under a snare: less certain
        peak = high[i:i + win].max()
        j = i + np.argmax(high[i:i + win])
        ring = 0
        while j + ring < len(high) and high[j + ring] > peak * 0.01 and ring * HOP / sr < 0.6:
            ring += 1
        cls = "open_hat" if ring * HOP / sr > 0.15 else "closed_hat"
        if cls == "open_hat":
            ring_until, ring_peak = j + ring, peak
        add(i, cls, ci, peak)

    # unclassified: clear full-band onsets that nothing above explains
    p, c = _peaks(_flux(S), k=3.0)
    if len(p):
        fv = np.array([full[i:i + win].max() for i in p])
        keep = fv > 0.05 * np.percentile(fv, 90)
        p, c = p[keep], c[keep]
    known = np.array(sorted(librosa.time_to_frames([h["time_s"] for h in hits], sr=sr, hop_length=HOP))) if hits else np.array([])
    for i, ci in zip(p, c):
        if not len(known) or np.min(np.abs(known - i)) > win:
            add(i, "unclassified", ci * 0.6, full[i:i + win].max())

    # Echoes: a hit's own decay can re-trigger 50–80 ms later with near-zero
    # strength (seen on snares and after open hats). Drop a weak hit (< 0.1)
    # that follows a hit of the same class — or any hit, for unclassified —
    # within 100 ms.
    hits.sort(key=lambda h: h["time_s"])
    kept = []
    for h in hits:
        prev = [k for k in kept if 0 < h["time_s"] - k["time_s"] <= 0.1
                and (k["class"] == h["class"] or h["class"] == "unclassified")]
        if prev and h["confidence"] < 0.1:
            continue
        kept.append(h)
    hits = kept

    # velocity: loudness within each class, 30..127
    for cls in GM:
        hs = [h for h in hits if h["class"] == cls]
        if not hs:
            continue
        v = np.log1p(np.array([h["_strength"] for h in hs]))
        lo, hi = np.percentile(v, 5), np.percentile(v, 95)
        for h, x in zip(hs, v):
            h["velocity"] = int(np.clip(30 + 97 * (x - lo) / (hi - lo + 1e-9), 30, 127))
    for h in hits:
        del h["_strength"]
    hits.sort(key=lambda h: (h["time_s"], h["pitch"]))
    return hits


def to_notes(hits: list[dict], length_s: float = 0.06) -> list[dict]:
    """Drum hits as notes for the manifest (fixed short length — drums are one-shots)."""
    return [{"start_s": h["time_s"], "end_s": round(h["time_s"] + length_s, 4), "pitch": h["pitch"],
             "velocity": h["velocity"], "confidence": h["confidence"], "class": h["class"],
             **({"flags": ["unclassified"]} if h["class"] == "unclassified" else {})}
            for h in hits]
