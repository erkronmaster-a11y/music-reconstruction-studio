"""Build plan for Ableton Live (Sprint 3): everything the Loomback Builder
device needs to assemble the arrangement, as one JSON file.

One rule for every audio file, whatever the timing mode: the clip sits at
arrangement beat 0 with Warp on, and warp markers pin sample times to beat
times. In constant mode two markers (start and end) place the audio without
any stretching. In beat-map mode one marker per beat straightens a drifting
song. MIDI notes use the same seconds→beats mapping, so audio and MIDI can't
disagree.

All beat positions are shifted by whole bars (`shift_beats`) so nothing starts
before the start of the arrangement (Live can't place audio at negative beats).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import beatmap, export, manifest

# Track order and look, following the brief: mix, vocals, bass, melody, drums, other stems.
ORDER = {"mix": 0, "vocals": 1, "bass": 2, "melody": 3, "drums": 4, "other": 5}
COLORS = {"mix": 0xEDF0F4, "vocals": 0xEFFF36, "bass": 0x2AA8FF, "melody": 0xFF3FBD, "drums": 0x48FF91, "other": 0x8FD3C9}
# Native instruments to try loading from Live's browser (best effort; names as in Live 12's browser).
INSTRUMENTS = {"bass": ["Bass", "Drift", "Analog", "Operator"], "melody": ["Drift", "Wavetable", "Analog", "Operator"],
               "drums": ["909 Core Kit", "808 Core Kit", "Drum Rack"]}
# Muted by default: the full mix and reference stems (the MIDI parts are what you hear and edit);
# vocals stay on, since they are kept as the original audio.
MUTED_AUDIO = {"mix", "bass", "drums", "melody", "other"}


def build(m: dict) -> dict:
    tl = export.add_shift(m, export.timeline(m))   # same mapping as the MIDI files
    bpb, shift = tl["beats_per_bar"], tl["shift_beats"]
    B = lambda t: round(export.raw_beats(m, tl, t) + shift, 5)

    tracks = []
    for s in m["sources"]:
        off = (s.get("sync") or {}).get("offset_s", 0.0)
        if tl["mode"] == "beatmap":
            bm = m["timing"]["detected"]["beat_map"]
            markers = [{"sample_time": 0.0, "beat_time": B(-off)}]
            markers += [{"sample_time": w["sample_time"], "beat_time": round(w["beat_time"] + shift, 5)}
                        for w in beatmap.warp_markers(bm, off, s["duration_s"]) if w["sample_time"] > 0.001]
            markers.append({"sample_time": round(s["duration_s"], 5), "beat_time": B(s["duration_s"] - off)})
        else:  # constant: start + end marker = no stretching, exact placement
            markers = [{"sample_time": 0.0, "beat_time": B(-off)},
                       {"sample_time": round(s["duration_s"], 5), "beat_time": B(s["duration_s"] - off)}]
        role = s["role"]
        tracks.append({"kind": "audio", "role": role, "name": "Original mix" if role == "mix" else f"{s['id'].title()} (stem)",
                       "file": s["path"], "color": COLORS.get(role, COLORS["other"]), "mute": role in MUTED_AUDIO,
                       "warp_mode": 6, "warp_markers": markers})
    for t in m["tracks"]:
        notes = []
        for n in manifest.effective_notes(t, "clean"):
            b0, b1 = B(n["start_s"]), B(n["end_s"])
            if b1 <= max(0.0, b0):
                continue
            notes.append({"pitch": int(n["pitch"]), "start_time": max(0.0, b0), "duration": round(max(0.01, b1 - b0), 5),
                          "velocity": int(n["velocity"])})
        tracks.append({"kind": "midi", "role": t["role"], "name": f"{t['id'].title()} MIDI", "color": COLORS.get(t["role"], COLORS["other"]),
                       "mute": False, "instrument_candidates": INSTRUMENTS.get(t["role"], []), "notes": notes,
                       "source": "raw detections (clean view) — not verified originals"})
    tracks.sort(key=lambda x: (ORDER.get(x["role"], 9) + (0.5 if x["kind"] == "midi" else 0), x["name"]))
    # vocals first among audio stems; MIDI parts right after their audio counterparts' block
    end_beats = max([w["beat_time"] for x in tracks if x["kind"] == "audio" for w in x["warp_markers"]] + [0])
    length = bpb * math.ceil(end_beats / bpb)
    return {"format": "loomback-live-plan", "version": 1, "project": m["name"], "tempo_bpm": round(tl["tempo_bpm"], 3),
            "beats_per_bar": bpb, "mode": tl["mode"], "shift_beats": shift, "length_beats": length,
            "song_starts_at_bar": int(shift // bpb) + 1, "tracks": tracks}


def write(m: dict, project_dir: str | Path, inbox: str | Path | None = None) -> Path:
    """Writes <project>/live-plan.json, and a copy into the Builder's inbox
    (<repo>/live/inbox/build.json) where the Max device looks for it."""
    plan = build(m)
    out = Path(project_dir) / "live-plan.json"
    out.write_text(json.dumps(plan))
    inbox = Path(inbox) if inbox else Path(__file__).resolve().parents[1] / "live" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "build.json").write_text(json.dumps(plan))
    return out


def instructions(plan: dict) -> str:
    """Manual fallback: how to rebuild the same Set by hand."""
    L = [f"Loomback — manual import for '{plan['project']}'", "",
         f"1. New Live Set. Set tempo to {plan['tempo_bpm']} BPM, 4/4.",
         "2. Audio: drag each file below onto its own audio track at bar 1 (1.1.1).",
         "   Turn Warp ON. Then place warp markers as listed (sample seconds → beat):"]
    for t in plan["tracks"]:
        if t["kind"] == "audio":
            wm = t["warp_markers"]
            L.append(f"   - {t['name']}: {t['file']}")
            L.append(f"     {len(wm)} markers; first {wm[0]}, last {wm[-1]}" + (" (constant tempo: just these two)" if len(wm) == 2 else ""))
    L += ["3. MIDI: drag the files from midi/ onto MIDI tracks at bar 1. Drums use General MIDI notes",
          "   (kick C1, snare D1, closed hat F#1, open hat A#1, other D#1) — any Drum Rack kit plays them.",
          f"   (Both the MIDI files and these markers use the same bar shift: song audio begins around bar {plan['song_starts_at_bar']}.)",
          "", "Notes are raw detections, not verified originals."]
    return "\n".join(L)
