"""Deterministic synthetic tests for band-limited drum onset detection.

Run: python -m unittest tests/test_onset_diagnostic.py -v
Dependencies: numpy, scipy. No audio assets or inference required.
"""
import unittest
import numpy as np
from scipy.signal import butter, sosfilt, find_peaks

SR = 24000
BANDS = {'kick': (35, 160), 'snare': (170, 2400), 'hat': (3500, 11000)}

def synth(kind, onset, seconds=2.0, sr=SR):
    rng = np.random.default_rng({'kick': 11, 'snare': 22, 'hat': 33}[kind])
    x = np.zeros(int(seconds * sr))
    start = int(round(onset * sr))
    t = np.arange(len(x) - start) / sr
    if kind == 'kick':
        wave = np.sin(2 * np.pi * (68 * t + 35 * (1 - np.exp(-t * 30)) / 30))
        env = (1 - np.exp(-t * 800)) * np.exp(-t * 22)
    else:
        wave = sosfilt(butter(3, BANDS[kind], fs=sr, btype='bandpass',
                              output='sos'), rng.standard_normal(len(t)))
        wave /= max(np.max(np.abs(wave)), 1e-12)
        env = (1 - np.exp(-t * 1500)) * np.exp(-t * (30 if kind == 'snare' else 65))
    x[start:] = wave * env
    return x

def candidates(x, kind, sr=SR, window_ms=5, min_distance_ms=70):
    """Bandpass -> nonoverlapping RMS -> positive energy change -> peaks."""
    y = sosfilt(butter(3, BANDS[kind], fs=sr, btype='bandpass',
                         output='sos'), x)
    width = round(sr * window_ms / 1000)
    y = y[:len(y) // width * width].reshape(-1, width)
    rms = np.sqrt(np.mean(y * y, axis=1))
    rises = np.maximum(0, np.diff(rms, prepend=0))
    threshold = max(float(np.quantile(rises, .75) * 1.5),
                    float(np.max(rises) * .06))
    peaks, _ = find_peaks(rises, height=threshold,
                          distance=round(min_distance_ms / window_ms))
    return (peaks + .5) * width / sr

def one_to_one(notes, peaks, tolerance=.06):
    """Globally nearest greedy matching with unique note and candidate IDs."""
    pairs = sorted((abs(p-n), i, j, p-n) for i, n in enumerate(notes)
                   for j, p in enumerate(peaks) if abs(p-n) <= tolerance)
    used_n, used_p, matches = set(), set(), []
    for _, i, j, signed in pairs:
        if i not in used_n and j not in used_p:
            used_n.add(i)
            used_p.add(j)
            matches.append((i, j, signed))
    return matches

class OnsetDiagnosticTests(unittest.TestCase):
    def test_isolated_known_onsets(self):
        for kind in BANDS:
            with self.subTest(kind=kind):
                onset = .6
                peaks = candidates(synth(kind, onset), kind)
                self.assertGreater(len(peaks), 0)
                self.assertLess(min(abs(peaks-onset)), .025)

    def test_no_false_onsets_in_silence(self):
        for kind in BANDS:
            self.assertEqual(len(candidates(np.zeros(SR), kind)), 0)

    def test_one_to_one_rejects_duplicate_notes(self):
        matches = one_to_one([.5, .502], [.503])
        self.assertEqual(len(matches), 1)
        self.assertAlmostEqual(matches[0][2], .001, places=6)

    def test_outside_tolerance_is_unmatched(self):
        self.assertEqual(one_to_one([.5], [.57], tolerance=.06), [])

    def test_overlapping_instruments_limit_class_specificity(self):
        """Cross-band leakage remains possible; identity is not verified."""
        x = synth('kick', .5) + synth('snare', .8) + synth('hat', 1.1)
        for kind, onset in [('kick', .5), ('snare', .8), ('hat', 1.1)]:
            peaks = candidates(x, kind)
            self.assertLess(min(abs(peaks-onset)), .03)

if __name__ == '__main__':
    unittest.main()
