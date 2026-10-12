"""Sprint 0 — does Basic Pitch run, and how does it compare with an alternative?

Ground truth is generated, not guessed: known MIDI parts are rendered to audio
with a simple harmonic synth, transcribed, and scored with mir_eval against the
exact notes that produced the audio.

Methods compared
  basic-pitch : Spotify Basic Pitch (polyphonic, instrument-agnostic NN)
  pyin        : librosa pYIN f0 tracking + onset splitting (monophonic, no NN)

Synthetic tones are easier than real mixes. These numbers say "the pipeline
works and roughly how methods rank", not "accuracy on your songs".

Usage: .venv/bin/python tools/probe_transcription.py
"""
import json
import platform
import resource
import time
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 22050
ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work" / "probe"
REPORT = ROOT / "reports" / "sprint0"
rng = np.random.default_rng(7)


# ---------- ground truth ----------
def make_part(n, lo, hi, bpm=120, jitter=0.012, legato=0.85):
    """Monophonic line on 8th notes with human microtiming. Returns [(start, end, midi)]."""
    beat = 60.0 / bpm
    notes, t, pitch = [], 0.5, (lo + hi) // 2
    for _ in range(n):
        step = rng.choice([1, 1, 2, 2, 4]) * beat / 2
        pitch = int(np.clip(pitch + rng.integers(-5, 6), lo, hi))
        start = t + rng.uniform(-jitter, jitter)
        dur = step * rng.uniform(0.4, legato)
        notes.append((round(start, 4), round(start + dur, 4), pitch))
        t += step
    return notes


def render(notes, harmonics):
    """Additive synth with a short attack and exponential decay."""
    end = max(e for _, e, _ in notes) + 0.5
    y = np.zeros(int(end * SR))
    for s, e, p in notes:
        f0 = 440.0 * 2 ** ((p - 69) / 12)
        n = int((e - s) * SR)
        t = np.arange(n) / SR
        env = np.minimum(1, t / 0.005) * np.exp(-t * 3) * np.minimum(1, (n - np.arange(n)) / (0.01 * SR))
        tone = sum(a * np.sin(2 * np.pi * f0 * (k + 1) * t) for k, a in enumerate(harmonics) if f0 * (k + 1) < SR / 2)
        i = int(s * SR)
        y[i:i + n] += 0.3 * env * tone
    return y / max(1e-9, np.abs(y).max()) * 0.8


# ---------- methods ----------
def run_basic_pitch(path, fmin, fmax):
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict
    _, _, events = predict(str(path), ICASSP_2022_MODEL_PATH,
                           minimum_frequency=fmin, maximum_frequency=fmax,
                           multiple_pitch_bends=False)
    return [(float(s), float(e), int(p)) for s, e, p, *_ in events]


def run_pyin(path, fmin, fmax):
    import librosa
    y, sr = librosa.load(str(path), sr=SR)
    hop = 256
    f0, voiced, _ = librosa.pyin(y, fmin=fmin, fmax=fmax, sr=sr, frame_length=2048, hop_length=hop)
    onsets = set(librosa.onset.onset_detect(y=y, sr=sr, hop_length=hop, backtrack=True).tolist())
    midi = np.where(voiced, np.round(librosa.hz_to_midi(np.nan_to_num(f0, nan=1.0))), -1)
    notes, cur, start = [], -1, 0
    for i, m in enumerate(list(midi) + [-1]):
        if m != cur or (i in onsets and cur != -1):
            if cur != -1 and (i - start) * hop / sr >= 0.04:
                notes.append((start * hop / sr, i * hop / sr, int(cur)))
            cur, start = m, i
    return notes


# ---------- scoring ----------
def score(ref, est):
    import mir_eval
    def arr(notes):
        if not notes:
            return np.zeros((0, 2)), np.zeros(0)
        a = np.array(notes, dtype=float)
        return a[:, :2], 440.0 * 2 ** ((a[:, 2] - 69) / 12)
    ri, rp = arr(ref)
    ei, ep = arr(est)
    on = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, onset_tolerance=0.05, offset_ratio=None)
    off = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, onset_tolerance=0.05, offset_ratio=0.2)
    m = mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=0.05, offset_ratio=None)
    onset_err = [abs(ri[i, 0] - ei[j, 0]) * 1000 for i, j in m]
    return {"ref_notes": len(ref), "est_notes": len(est),
            "onset_precision": round(on[0], 3), "onset_recall": round(on[1], 3), "onset_f1": round(on[2], 3),
            "onset_offset_f1": round(off[2], 3),
            "mean_onset_error_ms": round(float(np.mean(onset_err)), 1) if onset_err else None}


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    cases = {
        "bass (E1-E3, warm)": (make_part(40, 28, 52), [1, 0.5, 0.25, 0.12], 35, 200),
        "melody (C4-C6, bright)": (make_part(48, 60, 84), [1, 0.6, 0.4, 0.3, 0.2, 0.1], 200, 1200),
    }
    results = {"platform": f"{platform.system()} {platform.machine()} py{platform.python_version()}",
               "note": "Synthetic additive-synth audio; real mixes will score lower.", "cases": {}}
    import basic_pitch
    results["basic_pitch_version"] = getattr(basic_pitch, "__version__", "unknown")
    for name, (ref, harm, fmin, fmax) in cases.items():
        path = WORK / (name.split()[0] + ".wav")
        sf.write(path, render(ref, harm), SR)
        results["cases"][name] = {}
        for method, fn in [("basic-pitch", run_basic_pitch), ("pyin", run_pyin)]:
            t0 = time.time()
            try:
                est = fn(path, fmin, fmax)
                r = score(ref, est)
            except Exception as e:  # report, never hide
                r = {"error": repr(e)}
            r["seconds"] = round(time.time() - t0, 2)
            results["cases"][name][method] = r
            print(name, method, r)
    results["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 0)
    (REPORT / "transcription-probe.json").write_text(json.dumps(results, indent=2))
    print("peak RSS MB", results["peak_rss_mb"])


if __name__ == "__main__":
    main()
