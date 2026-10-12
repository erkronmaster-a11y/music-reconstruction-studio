"""Sprint 2: drums stem → GM drum MIDI, scored against rendered ground truth."""
import numpy as np
import pretty_midi
import pytest

from mrs import audio, drums, export, manifest, project, testsong


def f1(ref, est, tol=0.03):
    import mir_eval
    if not len(ref) or not len(est):
        return 0.0
    return mir_eval.onset.f_measure(np.array(ref), np.array(est), window=tol)[0]


@pytest.fixture(scope="module")
def song(tmp_path_factory):
    d = tmp_path_factory.mktemp("drums")
    truth = testsong.make(d, bars=24, stem_offsets={"drums": 0.012})
    return d, truth


@pytest.mark.parametrize("cls,minimum", [("kick", 0.9), ("snare", 0.9), ("closed_hat", 0.9), ("open_hat", 0.85)])
def test_classes_against_truth(song, cls, minimum):
    d, truth = song
    y, sr = audio.load(d / "Test Song drums.wav", sr=drums.SR)
    y = y[int(0.012 * sr):]   # this file was padded by 12 ms
    hits = drums.detect(y, sr)
    ref = [t for t, c in truth["notes"]["drums"] if c == cls]
    est = [h["time_s"] for h in hits if h["class"] == cls]
    assert f1(ref, est) >= minimum, (cls, f1(ref, est))


def test_pipeline_and_gm_midi(song, tmp_path):
    d, truth = song
    m, _ = project.build(folder=d)
    project.transcribe(m, ["drums"])
    t = manifest.track(m, "drums")
    notes = manifest.effective_notes(t)
    assert {n["pitch"] for n in notes} <= set(drums.GM.values())
    assert all("class" in n and 0 <= n["confidence"] <= 1 for n in notes)
    # sync offset removed: kicks land on the mix timeline within 10 ms (no quantising was applied)
    kicks = [n["start_s"] for n in notes if n["pitch"] == 36]
    ref = [tt for tt, c in truth["notes"]["drums"] if c == "kick"]
    errs = [min(abs(k - r) for r in ref) for k in kicks]
    assert np.median(errs) < 0.01
    info = export.write_midi(m, tmp_path / "midi")
    pm = pretty_midi.PrettyMIDI(str(tmp_path / "midi" / f"{m['name']} - drums.mid"))
    assert pm.instruments[0].is_drum and len(pm.instruments[0].notes) == len(notes)
