"""Build a project from a song folder: inspect, sync stems, detect timing."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from . import audio, beatmap, manifest, sync, tempo

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

    bm = beatmap.detect(str(mix_path))
    m["timing"]["detected"] = tempo.detect(y_mix, sr=sync.SR, rough_bpm=bm.get("live_tempo_bpm"))
    t = m["timing"]["detected"]
    t["beat_map"] = bm
    choose_mode(t)
    if bm.get("irregular_bars"):
        warnings.append(f"{len(bm['irregular_bars'])} bar(s) are not {bm['beats_per_bar']} beats long "
                        f"(first at {bm['irregular_bars'][0]['at_s']}s) — downbeats after them may sit off Live's bar lines")
    if t.get("downbeat_confidence", 0) < 0.15:
        warnings.append("first downbeat is uncertain — check it by ear (click track) and correct if needed")
    g = t.get("grid_gap_ms") or {}
    if g and g["last_third"] > 40 and g["last_third"] > 2 * g["first_third"]:
        warnings.append(f"beats drift away from a constant grid later in the song ({g['first_third']} → "
                        f"{g['last_third']} ms): the tempo itself may change — compare click-check.wav with click-follow.wav")
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
    bm = d.get("beat_map") or {}
    if d.get("export_mode"):
        g = d.get("constant_grid_gap_ms") or {}
        L.append(f"  export mode       {d['export_mode']} (one-tempo grid vs beat map: median {g.get('median')} ms, "
                 f"95% {g.get('p95')} ms)")
    if bm.get("beats_s"):
        L.append(f"  beat map          {len(bm['beats_s'])} beats, {len(bm['downbeats_s'])} downbeats, tempo "
                 f"{bm['tempo_range_bpm'][0]}–{bm['tempo_range_bpm'][1]} BPM → Live tempo {bm['live_tempo_bpm']} "
                 f"({bm['method'].split(' (')[0]})")
    if d.get("grid_gap_ms"):
        L.append(f"  grid fit          tracker said {d.get('tracker_tempo_bpm')} BPM; grid-to-beat gap "
                 f"{d['grid_gap_ms']['first_third']} ms early → {d['grid_gap_ms']['last_third']} ms late")
    if m.get("warnings"):
        L += ["", "Check:"] + [f"  - {w}" for w in m["warnings"]]
    return "\n".join(L)


def render_click(m: dict, out: str | Path, click_gain: float = 0.5, follow: bool = False) -> Path:
    """Mix + click on the effective grid (accent on the downbeat) — listen to check timing.
    follow=True clicks on the beat map (accent = detected downbeat) — what Live's
    warping will follow. Without a beat map: the tracker's beats, no accents."""
    import soundfile as sf
    src = manifest.mix(m)
    y, sr = audio.load(src["path"], sr=None, mono=True)
    eff = manifest.effective_timing(m)
    g = tempo.grid(eff["tempo_bpm"]["value"], eff["first_downbeat_s"]["value"], len(y) / sr,
                   eff["beats_per_bar"]["value"])
    if follow:
        d = m["timing"]["detected"]
        bm = d.get("beat_map") or {}
        if bm.get("beats_s"):  # beat map: accent on detected downbeats
            downs = set(bm["downbeats_s"])
            g = [{"time_s": b, "bar": 0, "beat": 1 if b in downs else 2} for b in bm["beats_s"]]
        else:
            g = [{"time_s": b, "bar": 0, "beat": 2} for b in d.get("tracker_beats_s", d["beats_s"])]
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


# ---------- Sprint 1b: which file to transcribe for each part ----------
def pick_sources(m: dict) -> dict[str, dict]:
    """bass ← bass stem; melody ← melody stem, else 'other' stem. No stem → the
    part is skipped and reported, rather than guessed from the full mix
    (the mix carries drums and vocals, which would come out as false notes)."""
    by_role: dict[str, list[dict]] = {}
    for s in m["sources"]:
        by_role.setdefault(s["role"], []).append(s)
    out = {}
    if by_role.get("bass"):
        out["bass"] = by_role["bass"][0]
    for role in ("melody", "other"):
        if by_role.get(role):
            out["melody"] = by_role[role][0]
            break
    return out


def transcribe(m: dict, parts: list[str] | None = None) -> list[str]:
    """Fills m['tracks'] raw layers. Returns messages (skips, timings)."""
    import time
    from . import manifest, transcribe as tr
    msgs = []
    chosen = pick_sources(m)
    for part in parts or ["bass", "melody"]:
        src = chosen.get(part)
        if not src:
            msgs.append(f"{part}: skipped — no {part} stem in this project "
                        f"(add a file with '{part}' in its name, or a Traktor .stem.mp4)")
            continue
        t0 = time.time()
        raw = tr.transcribe_source(src, part)
        manifest.set_raw_track(m, part, part, raw)
        msgs.append(f"{part}: {len(raw['notes'])} notes from '{src['id']}' via {raw['method']} "
                    f"({time.time() - t0:.1f}s)")
    return msgs


def redetect_timing(m: dict) -> dict:
    """Re-run timing detection on the mix (e.g. after a tempo-method upgrade).
    The user's correction, if any, is kept untouched."""
    src = manifest.mix(m)
    y, _ = audio.load(src["path"], sr=sync.SR)
    bm = beatmap.detect(src["path"])
    m["timing"]["detected"] = tempo.detect(y, sr=sync.SR, rough_bpm=bm.get("live_tempo_bpm"))
    m["timing"]["detected"]["beat_map"] = bm
    choose_mode(m["timing"]["detected"])
    return m


def choose_mode(t: dict, tol_ms: float = 20.0) -> None:
    """Simplest thing that fits: if one constant tempo stays within tol_ms of
    the beat map for 95 % of beats, export at constant tempo (no warping);
    otherwise use the beat map. The measured gap is stored either way."""
    bm = t.get("beat_map") or {}
    if not bm.get("beats_s"):
        t["export_mode"] = "constant"
        return
    b = np.asarray(bm["beats_s"])
    period = 60.0 / t["tempo_bpm"]
    d = (b - b[0]) / period
    # best phase: align grid to the beat map in a least-squares sense
    k = np.round(d)
    phase = float(np.mean(b - k * period))
    gap = np.abs(b - (phase + k * period)) * 1000
    t["constant_grid_gap_ms"] = {"median": round(float(np.median(gap)), 1), "p95": round(float(np.percentile(gap, 95)), 1)}
    t["export_mode"] = "constant" if t["constant_grid_gap_ms"]["p95"] <= tol_ms else "beatmap"
    if t["export_mode"] == "constant" and bm.get("downbeats_s"):
        # The grid fitted to every beat-map beat is the most precise anchor
        # (librosa's downbeat was ~16 ms late on a test song): put the first
        # downbeat on that grid, at Beat This!'s first downbeat.
        k0 = round((bm["downbeats_s"][0] - phase) / period)
        t["first_downbeat_s"] = round(phase + k0 * period, 4)
        t["first_downbeat_source"] = "beat map grid fit"
