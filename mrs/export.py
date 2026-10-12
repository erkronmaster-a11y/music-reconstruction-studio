"""Standard MIDI File export + review renders.

Timeline: MIDI time = audio time + `pad_s`, where pad_s puts the first downbeat
exactly on a bar line (so bar 2 in Live is the song's bar 1 when a pickup
exists, or bar 1 when the song starts on the one). The audio must be placed at
pad_s too — written to export.json for the Live builder (Sprint 3) and for
manual import. Notes are never quantised.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import audio, manifest

GM_PROGRAM = {"bass": 33, "melody": 81, "other": 0}  # Fingered Bass, Saw Lead, Piano


def timeline(m: dict) -> dict:
    """'beatmap' mode when a beat map exists (Live tempo constant, audio warped
    at every beat, notes placed by the map); else 'constant' (one tempo + pad)."""
    bm = (m["timing"]["detected"] or {}).get("beat_map") or {}
    if (bm.get("positions") and not m["timing"].get("correction")
            and (m["timing"]["detected"] or {}).get("export_mode", "beatmap") == "beatmap"):
        return {"mode": "beatmap", "tempo_bpm": bm["live_tempo_bpm"], "beats_per_bar": bm["beats_per_bar"],
                "first_downbeat_s": bm["downbeats_s"][0] if bm["downbeats_s"] else bm["beats_s"][0],
                "pad_s": 0.0, "first_downbeat_bar": int(bm["positions"][bm["beats_s"].index(
                    bm["downbeats_s"][0])] // bm["beats_per_bar"]) + 1 if bm["downbeats_s"] else 1,
                "beat_map_method": bm["method"], "sources": {"tempo_bpm": "detected (beat map)"}}
    eff = manifest.effective_timing(m)
    bpm = float(eff["tempo_bpm"]["value"])
    bpb = int(eff["beats_per_bar"]["value"] or 4)
    down = float(eff["first_downbeat_s"]["value"] or 0.0)
    bar_s = bpb * 60.0 / bpm
    pad = (bar_s - down % bar_s) % bar_s
    if pad < 1e-4:
        pad = 0.0
    return {"mode": "constant", "tempo_bpm": bpm, "beats_per_bar": bpb, "first_downbeat_s": down, "pad_s": round(pad, 6),
            "first_downbeat_bar": int(round((down + pad) / bar_s)) + 1,
            "sources": {k: v["source"] for k, v in eff.items()}}


def place(m: dict, tl: dict, t_s: float) -> float:
    """Mix-timeline seconds → seconds in the MIDI file (MIDI tempo = tl tempo)."""
    if tl["mode"] == "beatmap":
        from . import beatmap
        return float(beatmap.to_beats(m["timing"]["detected"]["beat_map"], t_s)[0]) * 60.0 / tl["tempo_bpm"]
    return t_s + tl["pad_s"]


def write_midi(m: dict, out_dir: str | Path) -> dict:
    import pretty_midi
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tl = timeline(m)
    files = {}
    for view, sub in (("clean", out_dir), ("raw", out_dir / "raw")):
        sub.mkdir(parents=True, exist_ok=True)
        combined = pretty_midi.PrettyMIDI(initial_tempo=tl["tempo_bpm"], resolution=960)
        combined.time_signature_changes.append(pretty_midi.TimeSignature(tl["beats_per_bar"], 4, 0))
        for t in m["tracks"]:
            pm = pretty_midi.PrettyMIDI(initial_tempo=tl["tempo_bpm"], resolution=960)
            pm.time_signature_changes.append(pretty_midi.TimeSignature(tl["beats_per_bar"], 4, 0))
            inst = pretty_midi.Instrument(program=GM_PROGRAM.get(t["role"], 0), name=f"{t['id']} ({view} transcription)")
            for n in manifest.effective_notes(t, view):
                s, e = place(m, tl, n["start_s"]), place(m, tl, n["end_s"])
                if e <= max(0.0, s):
                    continue
                inst.notes.append(pretty_midi.Note(velocity=int(n["velocity"]), pitch=int(n["pitch"]),
                                                   start=max(0.0, s), end=e))
            pm.instruments.append(inst)
            p = sub / f"{m['name']} - {t['id']}.mid"
            pm.write(str(p))
            combined.instruments.append(inst)
            if view == "clean":
                files[t["id"]] = p.name
        if m["tracks"]:
            combined.write(str(sub / f"{m['name']} - all.mid"))
    info = {"project": m["name"], "timeline": tl, "midi_files": files,
            "audio_placement": audio_placement(m, tl),
            "views": {"clean (this folder)": f"raw minus notes flagged {sorted(manifest.CLEAN_SKIPS)}",
                      "raw/": "every detected note"},
            "note": ("beatmap mode: set Live tempo to tempo_bpm, put every audio clip at bar 1 with Warp on and the "
                     "listed warp markers; MIDI files at bar 1. " if tl["mode"] == "beatmap" else
                     "constant mode: Live tempo = tempo_bpm; each audio file at start_s seconds, MIDI at bar 1. ")
                    + "Notes are raw detections, not verified originals."}
    (out_dir / "export.json").write_text(json.dumps(info, indent=2))
    return info


def audio_placement(m: dict, tl: dict) -> dict:
    out = {}
    for s in m["sources"]:
        off = (s.get("sync") or {}).get("offset_s", 0.0)
        if tl["mode"] == "beatmap":
            from . import beatmap
            out[s["id"]] = {"file": s["path"], "start_beats": 0.0, "warp": True,
                            "warp_markers": beatmap.warp_markers(m["timing"]["detected"]["beat_map"], off, s["duration_s"])}
        else:
            out[s["id"]] = {"file": s["path"], "start_s": round(tl["pad_s"] - off, 6), "warp": False}
    return out


def synth(notes: list[dict], dur_s: float, sr: int = 22050) -> np.ndarray:
    """Plain additive tones — for checking pitch and timing by ear, not for beauty."""
    y = np.zeros(int(dur_s * sr) + sr)
    for n in notes:
        f0 = 440.0 * 2 ** ((n["pitch"] - 69) / 12)
        L = int((n["end_s"] - n["start_s"]) * sr)
        if L <= 0:
            continue
        t = np.arange(L) / sr
        env = np.minimum(1, t / 0.005) * np.minimum(1, (L - np.arange(L)) / (0.01 * sr)) * (n["velocity"] / 127)
        tone = sum(a * np.sin(2 * np.pi * f0 * k * t) for k, a in ((1, 1), (2, .4), (3, .2)) if f0 * k < sr / 2)
        i = int(n["start_s"] * sr)
        if i < 0:
            continue
        seg = (env * tone)[: len(y) - i]
        y[i:i + len(seg)] += seg
    return y[: int(dur_s * sr)]


def review(m: dict, out_dir: str | Path) -> dict:
    """Per track: resynthesis alone, and an A/B file (left = source, right = resynthesis).
    Plus a rough chroma agreement — a listening aid, NOT an accuracy figure."""
    import librosa
    import soundfile as sf
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    srcs = {s["id"]: s for s in m["sources"]}
    sr = 22050
    stats = {}
    for t in m["tracks"]:
        src = srcs[t["source_id"]]
        y, _ = audio.load(src["path"], sr=sr)
        off = int(round((src.get("sync") or {}).get("offset_s", 0.0) * sr))
        y = y[off:] if off > 0 else np.concatenate([np.zeros(-off), y])  # stem → mix time
        notes = manifest.effective_notes(t)
        r = synth(notes, len(y) / sr, sr)
        n = min(len(y), len(r))
        y, r = y[:n], r[:n]
        norm = lambda v: v / (np.abs(v).max() + 1e-9) * 0.8
        sf.write(out_dir / f"{t['id']} - resynth.wav", norm(r), sr)
        sf.write(out_dir / f"{t['id']} - AB (L source, R resynth).wav", np.stack([norm(y), norm(r)], 1), sr)
        cy = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
        cr = librosa.feature.chroma_cqt(y=r, sr=sr, hop_length=512)
        active = librosa.feature.rms(y=y, hop_length=512)[0] > 0.02 * np.abs(y).max()  # frames where the source sounds
        k = min(cy.shape[1], cr.shape[1], len(active))
        num = (cy[:, :k] * cr[:, :k]).sum(0)
        den = np.linalg.norm(cy[:, :k], axis=0) * np.linalg.norm(cr[:, :k], axis=0) + 1e-9
        agree = float(np.mean((num / den)[active[:k]])) if active[:k].any() else None
        conf = [x["confidence"] for x in notes]
        stats[t["id"]] = {"notes": len(notes),
                          "pitch_range": [min(x["pitch"] for x in notes), max(x["pitch"] for x in notes)] if notes else None,
                          "low_confidence_notes(<0.3)": sum(c < 0.3 for c in conf),
                          "chroma_agreement_0to1": round(agree, 3) if agree is not None else None}
    (out_dir / "review.json").write_text(json.dumps(stats, indent=2))
    return stats
