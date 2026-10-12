"""Project manifest (project.json) — the single file every component reads.

Rules this format enforces:
  * Detected data and user corrections live side by side and never overwrite
    each other. `effective_*` helpers compute what is actually used.
  * All times are seconds from the start of the original mix. Bars and beats
    are derived from the timing, so fixing the tempo never moves a note.
  * Every detected item records the method that produced it.

Schema (version 1):
{
  "format": "mrs-project", "version": 1, "name": str, "created": iso8601,
  "tool": {"mrs": version, "python": version},
  "sources": [ {id, role, path, sha256, format, sample_rate, channels,
                duration_s, decoder,
                "sync": {offset_s, confidence, method} | null (the mix itself)} ],
  "timing": {
     "detected":   {method, tempo_bpm, beats_s[], beats_per_bar,
                    first_downbeat_s, downbeat_confidence, tempo_stability},
     "correction": null | {tempo_bpm?, first_downbeat_s?, beats_per_bar?, note?, time}
  },
  "tracks": []   # Sprint 1b: transcription layers (raw / corrections)
}
"""
from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from . import __version__

FORMAT, VERSION = "mrs-project", 1
ROLES = {"mix", "vocals", "bass", "drums", "melody", "other"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new(name: str) -> dict:
    return {"format": FORMAT, "version": VERSION, "name": name, "created": now(),
            "tool": {"mrs": __version__, "python": platform.python_version()},
            "sources": [], "timing": {"detected": None, "correction": None}, "tracks": []}


def load(path: str | Path) -> dict:
    m = json.loads(Path(path).read_text())
    if m.get("format") != FORMAT:
        raise ValueError(f"{path} is not an MRS project file")
    if m.get("version") != VERSION:
        raise ValueError(f"{path} has version {m.get('version')}, this tool reads {VERSION}")
    return m


def save(m: dict, path: str | Path) -> None:
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=2))
    tmp.replace(path)  # never leave a half-written project behind


def mix(m: dict) -> dict:
    for s in m["sources"]:
        if s["role"] == "mix":
            return s
    raise ValueError("project has no mix")


def correct_timing(m: dict, tempo_bpm: float | None = None, first_downbeat_s: float | None = None,
                   beats_per_bar: int | None = None, note: str | None = None) -> dict:
    """Record a user correction. Only given fields are set; detected data is untouched."""
    c = dict(m["timing"].get("correction") or {})
    if tempo_bpm is not None:
        if not 20 <= tempo_bpm <= 400:
            raise ValueError("tempo must be between 20 and 400 BPM")
        c["tempo_bpm"] = float(tempo_bpm)
    if first_downbeat_s is not None:
        if first_downbeat_s < 0:
            raise ValueError("first downbeat cannot be before the start of the file")
        c["first_downbeat_s"] = float(first_downbeat_s)
    if beats_per_bar is not None:
        c["beats_per_bar"] = int(beats_per_bar)
    if note:
        c["note"] = note
    c["time"] = now()
    m["timing"]["correction"] = c
    return m


def clear_timing_correction(m: dict) -> dict:
    m["timing"]["correction"] = None
    return m


def effective_timing(m: dict) -> dict:
    """What downstream steps use: the correction where given, else detection.
    Each value says where it came from."""
    d = m["timing"]["detected"] or {}
    c = m["timing"]["correction"] or {}
    out = {}
    for key in ("tempo_bpm", "first_downbeat_s", "beats_per_bar"):
        if key in c:
            out[key] = {"value": c[key], "source": "manual"}
        else:
            out[key] = {"value": d.get(key), "source": "detected"}
    return out


# ---------- transcription tracks (Sprint 1b) ----------
# track = {"id", "role", "source_id", "raw": {method, ..., notes[]},
#          "corrections": [] }   # corrections are written by the editor (Sprint 4), never by analysis

def set_raw_track(m: dict, track_id: str, role: str, raw: dict) -> dict:
    """Replace the raw layer of a track (re-analysis). Corrections are kept."""
    for t in m["tracks"]:
        if t["id"] == track_id:
            t["raw"] = {**raw, "created": now()}
            return t
    t = {"id": track_id, "role": role, "source_id": raw["source_id"], "raw": {**raw, "created": now()},
         "corrections": []}
    m["tracks"].append(t)
    return t


def track(m: dict, track_id: str) -> dict:
    for t in m["tracks"]:
        if t["id"] == track_id:
            return t
    raise KeyError(track_id)


CLEAN_SKIPS = {"possible_octave_ghost"}


def effective_notes(t: dict, view: str = "clean") -> list[dict]:
    """Raw notes with corrections applied, each tagged source='detected'.
    view='clean' leaves out notes flagged in CLEAN_SKIPS; view='raw' keeps all."""
    notes = [{**n, "source": "detected"} for n in t["raw"]["notes"]
             if view == "raw" or not (set(n.get("flags", [])) & CLEAN_SKIPS)]
    if t.get("corrections"):
        raise NotImplementedError("corrections are applied by the Sprint 4 editor")
    return notes
