"""Sprint 1b: transcription + MIDI export, scored against rendered ground truth."""
import json

import numpy as np
import pretty_midi
import pytest

from mrs import export, manifest, project, testsong


def score(ref, est, tol=0.05):
    import mir_eval
    hz = lambda p: 440.0 * 2 ** ((np.asarray(p, float) - 69) / 12)
    ri = np.array([[a, b] for a, b, _ in ref]); rp = hz([p for *_, p in ref])
    ei = np.array([[n["start_s"], n["end_s"]] for n in est]).reshape(-1, 2); ep = hz([n["pitch"] for n in est])
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, onset_tolerance=tol, offset_ratio=None)
    return p, r, f


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    d = tmp_path_factory.mktemp("song1b")
    truth = testsong.make(d, bars=12, stem_offsets={"bass": 0.015})
    m, _ = project.build(folder=d)
    msgs = project.transcribe(m)
    return m, truth, msgs, d


def test_bass_against_ground_truth(proj):
    m, truth, msgs, _ = proj
    p, r, f = score(truth["notes"]["bass"], manifest.track(m, "bass")["raw"]["notes"])
    print("bass P/R/F", p, r, f)
    assert f >= 0.85            # synthetic stem; real songs will be lower


def test_melody_against_ground_truth(proj):
    m, truth, *_ = proj
    p, r, f = score(truth["notes"]["melody"], manifest.effective_notes(manifest.track(m, "melody")))
    print("melody P/R/F", p, r, f)
    assert f >= 0.9


def test_sync_offset_removed(proj):
    """Bass stem was padded by 15 ms: notes must land on mix time, not stem time."""
    m, truth, *_ = proj
    est = manifest.track(m, "bass")["raw"]["notes"]
    errs = []
    for a, _, p in truth["notes"]["bass"]:
        near = [n["start_s"] - a for n in est if n["pitch"] == p and abs(n["start_s"] - a) < 0.05]
        if near:
            errs.append(min(near, key=abs))
    assert abs(np.median(errs)) < 0.012


def test_raw_layer_is_labelled(proj):
    m, *_ = proj
    t = manifest.track(m, "bass")
    assert t["corrections"] == [] and "pyin" in t["raw"]["method"] and t["raw"]["confidence_meaning"]
    assert all(n["source"] == "detected" for n in manifest.effective_notes(t))
    assert all(0 <= n["confidence"] <= 1 and 1 <= n["velocity"] <= 127 for n in t["raw"]["notes"])


def test_missing_stem_is_skipped_not_guessed(tmp_path):
    testsong.make(tmp_path, bars=2)
    for f in tmp_path.glob("*.wav"):
        if "MIX" not in f.name:
            f.unlink()
    m, _ = project.build(folder=tmp_path)
    msgs = project.transcribe(m)
    assert m["tracks"] == [] and all("skipped" in x for x in msgs)


def test_midi_export_alignment(proj, tmp_path):
    m, truth, *_ = proj
    info = export.write_midi(m, tmp_path / "midi")
    tl = info["timeline"]
    pm = pretty_midi.PrettyMIDI(str(tmp_path / "midi" / f"{m['name']} - bass.mid"))
    assert abs(pm.get_tempo_changes()[1][0] - tl["tempo_bpm"]) < 0.01
    # first downbeat + pad lands on a bar line
    bar_s = tl["beats_per_bar"] * 60 / tl["tempo_bpm"]
    pos = (tl["first_downbeat_s"] + tl["pad_s"]) / bar_s
    assert abs(pos - round(pos)) < 1e-6
    # a MIDI note sits exactly pad_s after its raw position (no quantising)
    raw = manifest.track(m, "bass")["raw"]["notes"][5]
    mid = sorted(pm.instruments[0].notes, key=lambda n: n.start)[5]
    assert abs(mid.start - (raw["start_s"] + tl["pad_s"])) < 0.002
    assert info["audio_placement"]["mix"]["start_s"] == pytest.approx(tl["pad_s"])
    assert info["audio_placement"]["bass"]["start_s"] == pytest.approx(tl["pad_s"] - 0.015, abs=1e-3)


def test_review_files(proj, tmp_path):
    m, *_ = proj
    stats = export.review(m, tmp_path / "rev")
    assert (tmp_path / "rev" / "bass - AB (L source, R resynth).wav").exists()
    assert stats["bass"]["chroma_agreement_0to1"] > 0.5
    json.loads((tmp_path / "rev" / "review.json").read_text())


def test_cli(proj, capsys):
    from mrs.__main__ import main
    m, _, _, d = proj
    p = d / "p.json"
    manifest.save(m, p)
    main(["export", str(p), "--no-review"])
    assert "first downbeat falls on bar" in capsys.readouterr().out


def test_octave_ghosts_flagged_not_deleted(proj, tmp_path):
    m, truth, *_ = proj
    t = manifest.track(m, "melody")
    raw, clean = manifest.effective_notes(t, "raw"), manifest.effective_notes(t, "clean")
    assert len(raw) > len(clean)                              # flagged notes still exist in raw
    assert all("possible_octave_ghost" in n.get("flags", []) for n in raw if n not in clean)
    export.write_midi(m, tmp_path / "midi")
    a = pretty_midi.PrettyMIDI(str(tmp_path / "midi" / f"{m['name']} - melody.mid"))
    b = pretty_midi.PrettyMIDI(str(tmp_path / "midi" / "raw" / f"{m['name']} - melody.mid"))
    assert len(b.instruments[0].notes) == len(raw) and len(a.instruments[0].notes) == len(clean)
