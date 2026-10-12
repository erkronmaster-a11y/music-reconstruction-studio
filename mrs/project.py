"""Build a project from a song folder: inspect, sync stems, detect timing."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from . import audio, manifest, sync, tempo

AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a"}
# File-name keywords → role, checked in this order. Stem words come before mix
# words: song titles often appear in every file name ("My Song - Bass.wav"), so
# the mix is only what is left once no stem word matches.
ROLE_WORDS = [
    ("vocals", r"vocal|vox|voice|acapella"),
    ("drums", r"drum|perc|kick|snare|hat"),
    ("bass", r"bass|\bsub\b"),
    ("melody", r"melody|lead|synth|keys|piano|guitar"),
    ("mix", r"\b(mix|master|mixdown|full|main)\b"),
]
SYNC_WARN_S = 0.005   # 5 ms: audible flam if stems are off by more
DUR_WARN_S = 0.5


def guess_role(name: str) -> str:
    n = re.sub(r"[_\-.]+", " ", name.lower())
    for role, pat in ROLE_WORDS:
        if re.search(pat, n):
            return role
    return "other"


def scan_folder(folder: Path) -> dict[str, list[Path]]:
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in AUDIO_EXT and not p.name.startswith("."))
    if not files:
        raise ValueError(f"No audio files in {folder}")
    roles: dict[str, list[Path]] = {}
    for f in files:
        roles.setdefault(guess_role(f.stem), []).append(f)
    if len(files) == 1:
        return {"mix": files}
    if len(roles.get("mix", [])) != 1:
        found = ", ".join(f.name for f in roles.get("mix", [])) or "none"
        raise ValueError(f"Need exactly one full mix in {folder} (a file name containing 'mix', 'master' "
                         f"or 'full'). Found: {found}. Rename the files and try again.")
    return roles


def build(folder: str | Path | None = None, mix_path: str | Path | None = None,
          stems: dict[str, str | Path] | None = None, name: str | None = None) -> tuple[dict, list[str]]:
    """Returns (manifest, warnings)."""
    if folder:
        roles = scan_folder(Path(folder))
        mix_path = roles.pop("mix")[0]
        stems = {}
        for role, paths in roles.items():
            for i, p in enumerate(paths):
                stems[role if len(paths) == 1 else f"{role}{i + 1}"] = p
    if not mix_path:
        raise ValueError("A full mix is required")
    stems = stems or {}
    m = manifest.new(name or Path(folder or mix_path).stem)
    warnings: list[str] = []

    info = audio.inspect(mix_path)
    m["sources"].append({"id": "mix", "role": "mix", **info.as_dict(), "sync": None})
    y_mix, _ = audio.load(mix_path, sr=sync.SR)

    for sid, p in stems.items():
        si = audio.inspect(p)
        y, _ = audio.load(p, sr=sync.SR)
        s = sync.estimate_offset(y_mix, y)
        role = re.sub(r"\d+$", "", sid)
        m["sources"].append({"id": sid, "role": role if role in manifest.ROLES else "other", **si.as_dict(), "sync": s})
        if si.sample_rate != info.sample_rate:
            warnings.append(f"{sid}: sample rate {si.sample_rate} Hz differs from mix {info.sample_rate} Hz")
        if abs(si.duration_s - info.duration_s) > DUR_WARN_S:
            warnings.append(f"{sid}: length {si.duration_s:.2f}s differs from mix {info.duration_s:.2f}s")
        if abs(s["offset_s"]) > SYNC_WARN_S:
            warnings.append(f"{sid}: starts {s['offset_s'] * 1000:+.1f} ms relative to the mix "
                            f"(confidence {s['confidence']}); it will be shifted to line up")

    m["timing"]["detected"] = tempo.detect(y_mix, sr=sync.SR)
    t = m["timing"]["detected"]
    if t.get("downbeat_confidence", 0) < 0.15:
        warnings.append("first downbeat is uncertain — check it by ear (click track) and correct if needed")
    if t.get("tempo_stability") and t["tempo_stability"] > 0.03:
        warnings.append(f"beat spacing varies ({t['tempo_stability']:.1%}) — tempo may drift or the tracker struggled")
    m["warnings"] = warnings
    return m, warnings


def summary(m: dict) -> str:
    L = [f"Project: {m['name']}", ""]
    L.append(f"{'source':10} {'format':6} {'rate':>6} {'ch':>2} {'length':>9}  sync")
    for s in m["sources"]:
        sy = "reference" if s["sync"] is None else f"{s['sync']['offset_s'] * 1000:+.1f} ms (conf {s['sync']['confidence']})"
        L.append(f"{s['id']:10} {s['format']:6} {s['sample_rate']:>6} {s['channels']:>2} {s['duration_s']:>8.2f}s  {sy}")
    eff = manifest.effective_timing(m)
    d = m["timing"]["detected"] or {}
    L += ["", "Timing (value · where it came from)"]
    for k in ("tempo_bpm", "first_downbeat_s", "beats_per_bar"):
        L.append(f"  {k:17} {eff[k]['value']}  · {eff[k]['source']}")
    L.append(f"  detected beats    {len(d.get('beats_s', []))}, downbeat confidence {d.get('downbeat_confidence')}, "
             f"beat spacing spread {d.get('tempo_stability')}")
    if m.get("warnings"):
        L += ["", "Check:"] + [f"  - {w}" for w in m["warnings"]]
    return "\n".join(L)


def render_click(m: dict, out: str | Path, click_gain: float = 0.5) -> Path:
    """Mix + click on the effective grid (accent on the downbeat) — listen to check timing."""
    import soundfile as sf
    src = manifest.mix(m)
    y, sr = audio.load(src["path"], sr=None, mono=True)
    eff = manifest.effective_timing(m)
    g = tempo.grid(eff["tempo_bpm"]["value"], eff["first_downbeat_s"]["value"], len(y) / sr,
                   eff["beats_per_bar"]["value"])
    n = int(0.03 * sr)
    t = np.arange(n) / sr
    env = np.exp(-t * 150)
    for b in g:
        f = 1760 if b["beat"] == 1 else 880
        i = int(b["time_s"] * sr)
        if 0 <= i < len(y):
            seg = (env * np.sin(2 * np.pi * f * t))[: len(y) - i]
            y[i:i + len(seg)] += click_gain * seg
    peak = np.abs(y).max()
    if peak > 1:
        y /= peak
    out = Path(out)
    sf.write(out, np.stack([y, y], 1), sr)
    return out
