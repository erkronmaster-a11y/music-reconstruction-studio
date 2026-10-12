"""Stem synchronisation: is each stem time-aligned with the mix?

Stems exported from the same session normally start at sample 0 together, but
early AI tools sometimes pad or trim. We measure, we don't assume.

Method: FFT cross-correlation of the raw waveforms. The mix contains the stem,
so the correlation peaks sharply at the true lag. (An onset-envelope version
was tried first: on rhythmic stems it locked onto a lag one beat away, because
envelopes repeat every beat; waveforms don't.)

offset_s > 0 means the stem's content happens *later* than in the mix, i.e. the
stem must be moved earlier by offset_s to line up.
confidence = normalised correlation at the peak (0..1): roughly "how much of
this stem is audibly present in the mix at that alignment".
"""
from __future__ import annotations

import numpy as np
from scipy.signal import correlate

SR = 22050


def estimate_offset(mix: np.ndarray, stem: np.ndarray, sr: int = SR, max_offset_s: float = 10.0) -> dict:
    n = min(len(mix), len(stem))
    a, b = mix[:n].astype(np.float64), stem[:n].astype(np.float64)
    nb = np.linalg.norm(b)
    if n < sr // 10 or nb == 0:
        return {"offset_s": 0.0, "confidence": 0.0, "method": "waveform-xcorr", "note": "stem silent or too short"}
    xc = correlate(b, a, mode="full", method="fft")
    lags = np.arange(-n + 1, n)
    keep = np.abs(lags) <= int(max_offset_s * sr)
    xc, lags = xc[keep], lags[keep]
    k = int(np.argmax(xc))
    lag = int(lags[k])
    # Normalise by the energy of the overlapping parts.
    if lag >= 0:
        sa, sb = a[:n - lag], b[lag:]
    else:
        sa, sb = a[-lag:], b[:n + lag]
    conf = float(xc[k] / (np.linalg.norm(sa) * np.linalg.norm(sb) + 1e-12))
    return {"offset_s": round(lag / sr, 5), "confidence": round(max(0.0, conf), 3), "method": "waveform-xcorr"}
