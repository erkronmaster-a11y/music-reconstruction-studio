"""Sprint 0 checks that run without a Mac: the device file and the test tone."""
import json
import struct
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_amxd_container_is_well_formed():
    subprocess.run([sys.executable, str(ROOT / "tools/build_amxd.py")], check=True)
    data = (ROOT / "live/MRS Bridge.amxd").read_bytes()
    assert data[:4] == b"ampf" and data[8:12] == b"mmmm"
    assert data[24:28] == b"ptch"
    (length,) = struct.unpack("<I", data[28:32])
    body = data[32:]
    assert len(body) == length
    patch = json.loads(body.rstrip(b"\x00\n"))["patcher"]
    texts = [b["box"].get("text") for b in patch["boxes"]]
    assert "js mrs_bridge.js" in texts and "run" in texts and "verify" in texts


def test_bridge_script_exists_next_to_device():
    assert (ROOT / "live/mrs_bridge.js").is_file()


def test_test_tone():
    subprocess.run([sys.executable, str(ROOT / "tools/make_test_tone.py")], check=True)
    with wave.open(str(ROOT / "assets/test-tone.wav")) as w:
        assert w.getframerate() == 44100 and w.getnframes() == 88200
