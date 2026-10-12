"""Decoding and inspection.

WAV, AIFF, FLAC and MP3 are read by libsndfile (bundled with `soundfile`).
Anything else (m4a, …) goes through ffmpeg, if one is installed.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

# Homebrew's ffmpeg first: some Macs have a 2015 ffmpeg earlier on PATH.
FFMPEG_CANDIDATES = ["/opt/homebrew/bin/ffmpeg", "/usr/local/opt/ffmpeg/bin/ffmpeg"]


@dataclass
class AudioInfo:
    path: str
    format: str
    subtype: str
    sample_rate: int
    channels: int
    frames: int
    duration_s: float
    sha256: str
    decoder: str

    def as_dict(self) -> dict:
        return asdict(self)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ffmpeg_path() -> str | None:
    for c in FFMPEG_CANDIDATES:
        if Path(c).exists():
            return c
    return shutil.which("ffmpeg")


def inspect(path: str | Path) -> AudioInfo:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        i = sf.info(str(path))
        return AudioInfo(str(path), i.format, i.subtype, i.samplerate, i.channels, i.frames,
                         i.frames / i.samplerate, sha256(path), "libsndfile")
    except sf.LibsndfileError:
        y, sr = _ffmpeg_decode(path)
        return AudioInfo(str(path), path.suffix.lstrip(".").upper(), "ffmpeg", sr, y.shape[1],
                         y.shape[0], y.shape[0] / sr, sha256(path), "ffmpeg")


def load(path: str | Path, sr: int | None = None, mono: bool = True) -> tuple[np.ndarray, int]:
    """Returns float32 audio, shape (frames,) if mono else (frames, channels)."""
    path = Path(path)
    try:
        y, file_sr = sf.read(str(path), dtype="float32", always_2d=True)
    except sf.LibsndfileError:
        y, file_sr = _ffmpeg_decode(path)
    if mono:
        y = y.mean(axis=1)
    if sr and sr != file_sr:
        import librosa
        y = librosa.resample(y.T if not mono else y, orig_sr=file_sr, target_sr=sr)
        y = y if mono else y.T
        file_sr = sr
    return y.astype(np.float32), file_sr


def _ffmpeg_decode(path: Path) -> tuple[np.ndarray, int]:
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError(f"Cannot decode {path.name}: not a WAV/AIFF/FLAC/MP3 and ffmpeg is not installed.")
    probe = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    sr, ch = 44100, 2
    for line in probe.splitlines():
        if "Audio:" in line:
            parts = [p.strip() for p in line.split(",")]
            for p in parts:
                if p.endswith(" Hz"):
                    sr = int(p.split()[0])
            if "mono" in line:
                ch = 1
            break
    raw = subprocess.run([ff, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", str(ch), "-ar", str(sr), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, ch), sr
