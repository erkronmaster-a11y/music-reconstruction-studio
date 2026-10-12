"""Sprint 1a: decoding, stem sync, tempo/downbeat, manifest — against rendered ground truth."""
import json
import shutil

import numpy as np
import pytest

from mrs import audio, manifest, project, tempo, testsong


@pytest.fixture(scope="module")
def song(tmp_path_factory):
    d = tmp_path_factory.mktemp("song")
    truth = testsong.make(d, stem_offsets={"bass": 0.020}, formats=("wav",))
    return d, truth


@pytest.fixture(scope="module")
def built(song):
    d, _ = song
    return project.build(folder=d)


@pytest.mark.parametrize("fmt", ["wav", "aiff", "flac", "mp3"])
def test_decode_formats(tmp_path, fmt):
    testsong.make(tmp_path, bars=2, formats=(fmt,))
    f = next(tmp_path.glob(f"*MIX.{fmt}"))
    info = audio.inspect(f)
    y, sr = audio.load(f, sr=22050)
    assert info.sample_rate == 44100 and info.channels == 2
    assert abs(info.duration_s - len(y) / sr) < 0.06  # mp3 adds encoder padding
    assert np.abs(y).max() > 0.1


def test_roles_from_file_names(song):
    d, _ = song
    roles = project.scan_folder(d)
    assert [p.name for p in roles["mix"]] == ["Test Song MIX.wav"]
    assert {"vocals", "drums", "bass", "melody"} <= set(roles)


def test_needs_exactly_one_mix(tmp_path, song):
    d, _ = song
    for f in d.glob("*.wav"):
        if "MIX" not in f.name:
            shutil.copy(f, tmp_path / f.name)
    with pytest.raises(ValueError, match="exactly one full mix"):
        project.scan_folder(tmp_path)


def test_stem_sync(built, song):
    m, warnings = built
    by = {s["id"]: s for s in m["sources"]}
    assert abs(by["bass"]["sync"]["offset_s"] - 0.020) < 0.001       # padded 20 ms: found to the ms
    for sid in ("drums", "melody", "vocals"):
        assert abs(by[sid]["sync"]["offset_s"]) < 0.001
    assert any(w.startswith("bass:") for w in warnings)


def test_tempo_and_downbeat(built, song):
    m, _ = built
    _, truth = song
    d = m["timing"]["detected"]
    assert abs(d["tempo_bpm"] - truth["bpm"]) / truth["bpm"] < 0.01
    period = 60 / truth["bpm"]
    # beats land on the true grid (within 30 ms)
    errs = [min(abs((b - truth["first_downbeat_s"]) / period - round((b - truth["first_downbeat_s"]) / period)) * period, 1)
            for b in d["beats_s"]]
    assert np.median(errs) < 0.03
    assert abs(d["first_downbeat_s"] - truth["first_downbeat_s"]) < 0.03


def test_correction_never_touches_detection(built, tmp_path):
    m, _ = built
    m = json.loads(json.dumps(m))
    before = json.dumps(m["timing"]["detected"])
    manifest.correct_timing(m, tempo_bpm=61.5, note="half time feel")
    eff = manifest.effective_timing(m)
    assert eff["tempo_bpm"] == {"value": 61.5, "source": "manual"}
    assert eff["first_downbeat_s"]["source"] == "detected"
    assert json.dumps(m["timing"]["detected"]) == before
    manifest.save(m, tmp_path / "p.json")
    assert manifest.load(tmp_path / "p.json")["timing"]["correction"]["tempo_bpm"] == 61.5
    manifest.clear_timing_correction(m)
    assert manifest.effective_timing(m)["tempo_bpm"]["source"] == "detected"


def test_correction_validation(built):
    m, _ = built
    with pytest.raises(ValueError):
        manifest.correct_timing(json.loads(json.dumps(m)), tempo_bpm=5)


def test_grid_and_click(built, tmp_path):
    m, _ = built
    g = tempo.grid(120, 0.9, 4.0)
    assert g[0] == {"time_s": 0.4, "bar": 0, "beat": 4}          # pickup beat before bar 1
    assert [b for b in g if b["bar"] == 1][0] == {"time_s": 0.9, "bar": 1, "beat": 1}
    out = project.render_click(m, tmp_path / "click.wav")
    assert out.stat().st_size > 1000


def test_cli_end_to_end(song, tmp_path, capsys):
    from mrs.__main__ import main
    d, _ = song
    main(["analyze", str(d), "--out", str(tmp_path / "p")])
    main(["tempo", str(tmp_path / "p/project.json"), "--downbeat", "0.5"])
    out = capsys.readouterr().out
    assert "0.5  · manual" in out


def _make_stem_mp4(song_dir, out, with_meta=True):
    """Build an NI-style .stem.mp4 (5 AAC streams + optional 'stem' metadata box)."""
    import subprocess
    from mrs.audio import ffmpeg_path
    files = ["Test Song MIX.wav"] + [f"Test Song {n}.wav" for n in ("drums", "bass", "melody", "vocals")]
    cmd = [ffmpeg_path(), "-v", "error", "-y"]
    for f in files:
        cmd += ["-i", str(song_dir / f)]
    for i in range(5):
        cmd += ["-map", f"{i}:a"]
    subprocess.run(cmd + ["-c:a", "aac", "-b:a", "256k", str(out)], check=True)
    if with_meta:  # append moov/udta/stem the way NI does, by rewriting the moov box
        import struct
        data = bytearray(out.read_bytes())
        meta = json.dumps({"stems": [{"name": n, "color": "#ffffff"} for n in ("Drums", "Bass", "Synths", "Vocals")]}).encode()
        stem_box = struct.pack(">I4s", 8 + len(meta), b"stem") + meta
        udta = struct.pack(">I4s", 8 + len(stem_box), b"udta") + stem_box
        i = 0
        while i < len(data):
            size, typ = struct.unpack(">I4s", data[i:i + 8])
            if typ == b"moov":
                data[i:i + 4] = struct.pack(">I", size + len(udta))
                data[i + size:i + size] = udta
                break
            i += size
        # moov sits after mdat with ffmpeg's default layout, so no chunk offsets move.
        out.write_bytes(bytes(data))


def test_ni_stem_file_extract_and_analyze(song, tmp_path):
    from mrs import nistem
    d, truth = song
    # use an aligned copy of the song (the module song has a padded bass stem)
    aligned = tmp_path / "aligned"
    testsong.make(aligned, bars=8)
    f = tmp_path / "Test Song.stem.mp4"
    _make_stem_mp4(aligned, f)
    assert nistem.stem_names(f) == ["Drums", "Bass", "Synths", "Vocals"]
    out = nistem.extract(f, tmp_path / "x")
    assert set(out) == {"mix", "drums", "bass", "melody", "vocals"}  # "Synths" → melody
    m, _ = project.build(folder=tmp_path / "x")
    for s in m["sources"]:
        if s["sync"]:
            assert abs(s["sync"]["offset_s"]) < 0.0005, s   # same timeline → aligned to < 0.5 ms


def test_ni_stem_without_metadata_uses_default_order(song, tmp_path):
    from mrs import nistem
    aligned = tmp_path / "a"
    testsong.make(aligned, bars=2)
    f = tmp_path / "Plain.stem.mp4"
    _make_stem_mp4(aligned, f, with_meta=False)
    assert nistem.read_metadata(f) is None
    assert nistem.stem_names(f) == nistem.DEFAULT_NAMES
