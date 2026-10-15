"""Sprint 3: the Ableton build plan agrees with the MIDI export and is valid for Live."""
import json

import numpy as np
import pretty_midi
import pytest

from mrs import export, liveplan, manifest, project, testsong


@pytest.fixture(scope="module", params=["constant", "beatmap"])
def built(request, tmp_path_factory):
    d = tmp_path_factory.mktemp("s3")
    testsong.make(d, bars=8, stem_offsets={"bass": 0.02})
    m, _ = project.build(folder=d)
    project.transcribe(m, ["bass", "drums"])
    m["timing"]["detected"]["export_mode"] = request.param
    m["timing"]["warp_per_beat"] = request.param == "beatmap"
    return m, request.param, tmp_path_factory.mktemp("out")


def test_plan_shape(built):
    m, mode, out = built
    plan = liveplan.build(m)
    assert plan["mode"] == mode and plan["tempo_bpm"] > 0
    kinds = [t["kind"] for t in plan["tracks"]]
    assert kinds.count("audio") == len(m["sources"]) and kinds.count("midi") == 2
    assert plan["tracks"][0]["name"] == "Original mix" and plan["tracks"][0]["mute"]
    for t in plan["tracks"]:
        if t["kind"] == "audio":
            wm = t["warp_markers"]
            assert wm[0]["sample_time"] == 0.0 and wm[0]["beat_time"] >= 0           # nothing before beat 0
            b = [w["beat_time"] for w in wm]; s = [w["sample_time"] for w in wm]
            assert all(np.diff(b) > 0) and all(np.diff(s) > 0)                      # monotonic, as Live requires
            bpm = np.diff(b) / (np.diff(s) / 60)
            assert bpm.min() >= 5 and bpm.max() <= 999                              # Live's allowed range
        else:
            assert t["notes"] and all(n["start_time"] >= 0 and n["duration"] > 0 for n in t["notes"])


def test_plan_matches_midi_files(built):
    """The device builds from the plan; the manual fallback uses midi/. Same beats."""
    m, mode, out = built
    plan = liveplan.build(m)
    export.write_midi(m, out / f"midi-{mode}")
    pm = pretty_midi.PrettyMIDI(str(out / f"midi-{mode}" / f"{m['name']} - bass.mid"))
    bpm = plan["tempo_bpm"]
    midi_beats = sorted(round(n.start * bpm / 60, 3) for n in pm.instruments[0].notes)
    plan_beats = sorted(round(n["start_time"], 3) for n in next(t for t in plan["tracks"] if t["name"] == "Bass MIDI")["notes"])
    assert len(midi_beats) == len(plan_beats)
    assert max(abs(a - b) for a, b in zip(midi_beats, plan_beats)) < 0.01


def test_stem_offset_in_markers(built):
    m, mode, out = built
    plan = liveplan.build(m)
    mix = next(t for t in plan["tracks"] if t["role"] == "mix")["warp_markers"]
    bass = next(t for t in plan["tracks"] if t["kind"] == "audio" and t["role"] == "bass")["warp_markers"]
    # bass stem is 20 ms late: its sample 0 sits 20 ms (in beats) before the mix's sample 0
    assert bass[0]["beat_time"] == pytest.approx(mix[0]["beat_time"] - 0.02 * plan["tempo_bpm"] / 60, abs=0.01)


def test_write_and_instructions(built, tmp_path):
    m, mode, out = built
    p = liveplan.write(m, tmp_path, inbox=tmp_path / "inbox")
    plan = json.loads((tmp_path / "inbox" / "build.json").read_text())
    assert plan == json.loads(p.read_text())
    txt = liveplan.instructions(plan)
    assert str(plan["tempo_bpm"]) in txt and "Warp ON" in txt


def test_builder_warp_markers_in_simulated_live(built, tmp_path):
    """Runs live/loomback_build.js's marker code against a simulation of Live 12.0.15's
    rules seen on the Mac (hidden helper marker; explicit adds only between markers)."""
    import shutil, subprocess
    if not shutil.which("node"):
        pytest.skip("node not installed")
    m, mode, out = built
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(liveplan.build(m)))
    r = subprocess.run(["node", "tools/mock_live_warp.js", "live/loomback_build.js", str(plan)],
                       capture_output=True, text=True, check=True)
    res = json.loads(r.stdout.strip().splitlines()[-1])
    # Live 12.0.15 refuses adds: the clip must still start and end exactly where the plan says
    assert res["error"] is None and res["check"]["start_error_beats"] == 0 and abs(res["check"]["end_error_beats"]) < 0.01, res
    if mode == "constant":
        assert res["worst_deviation_beats"] < 0.005, res


def test_constant_mode_places_unwarped_audio_exactly(built):
    """Warp off: a file played at true speed from position_beats must meet the MIDI
    mapping at both ends, i.e. position + duration*tempo/60 == the plan's end beat."""
    m, mode, out = built
    plan = liveplan.build(m)
    for t in plan["tracks"]:
        if t["kind"] != "audio":
            continue
        assert t["warp"] == (mode == "beatmap")
        if mode == "constant":
            first, last = t["warp_markers"][0], t["warp_markers"][-1]
            assert t["position_beats"] == first["beat_time"] >= 0
            assert last["beat_time"] == pytest.approx(t["position_beats"] + last["sample_time"] * plan["tempo_bpm"] / 60, abs=0.001)


def test_unwarped_clip_plays_from_file_start_in_simulated_live(built, tmp_path):
    """Live puts a new clip's start marker on the first sound; warp-off placement
    must move it back to 0:00 or the stem plays early by its lead-in (Mac run 4)."""
    import os, shutil, subprocess
    if not shutil.which("node"):
        pytest.skip("node not installed")
    m, mode, out = built
    plan = liveplan.build(m)
    if mode != "constant":
        pytest.skip("warp-off placement is the constant-tempo path")
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(plan))
    r = subprocess.run(["node", "tools/mock_live_warp.js", "live/loomback_build.js", str(p), "0.045"],
                       capture_output=True, text=True, check=True, env={**os.environ, "UNWARPED": "1"})
    res = json.loads(r.stdout.strip().splitlines()[-1])
    assert res["error"] is None, res
    assert res["props"]["start_marker"] == 0 and res["props"]["warping"] == 0, res
    assert res["check"]["start_error_beats"] == 0, res
