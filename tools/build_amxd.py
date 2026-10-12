"""Build live/MRS Bridge.amxd — a tiny Max MIDI Effect that hosts mrs_bridge.js.

The .amxd container is: b"ampf" chunk (device type), b"meta" chunk, then a
b"ptch" chunk holding the plain-JSON Max patcher. We write it unfrozen, so
the device loads mrs_bridge.js from the same folder.

If Live refuses this file, build the device by hand instead — see
SETUP_MACOS.md, "Fallback: build the device by hand" (2 minutes).

Usage: python3 tools/build_amxd.py
"""
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "live" / "MRS Bridge.amxd"
BUILDER = ROOT / "live" / "Loomback Builder.amxd"


def box(id_, maxclass, text, rect, ins=1, outs=1, **extra):
    b = {"id": id_, "maxclass": maxclass, "numinlets": ins, "numoutlets": outs,
         "patching_rect": rect}
    if outs:
        b["outlettype"] = [""] * outs
    if text is not None:
        b["text"] = text
    b.update(extra)
    return {"box": b}


def line(src, dst, inlet=0, outlet=0):
    return {"patchline": {"source": [src, outlet], "destination": [dst, inlet]}}


def patcher(js="mrs_bridge.js", status="click run, then save/close/reopen, then verify",
            note="MRS Bridge — Sprint 0 test. Results go to reports/sprint0/.", buttons=("run", "verify")):
    boxes = [
        box("run", "message", buttons[0], [10, 10, 40, 22], ins=2),
        box("verify", "message", buttons[1], [60, 10, 50, 22], ins=2),
        box("js", "newobj", f"js {js}", [10, 45, 140, 22],
            saved_object_attributes={"filename": js, "parameter_enable": 0}),
        box("status", "message", status, [10, 80, 700, 60], ins=2),
        box("note", "comment", note, [10, 148, 500, 20], outs=0),
        # Keep MIDI flowing through, so the device is harmless on any track.
        box("midiin", "newobj", "midiin", [430, 10, 45, 22], outs=1),
        box("midiout", "newobj", "midiout", [430, 45, 50, 22], outs=0),
    ]
    lines = [line("run", "js"), line("verify", "js"), line("js", "status"),
             line("midiin", "midiout")]
    return {"patcher": {
        "fileversion": 1,
        "appversion": {"major": 8, "minor": 6, "revision": 0, "architecture": "x64", "modernui": 1},
        "classnamespace": "box",
        "rect": [100.0, 100.0, 640.0, 300.0],
        "openinpresentation": 0,
        "default_fontsize": 10.0, "default_fontface": 0, "default_fontname": "Arial Bold",
        "gridonopen": 1, "gridsize": [8.0, 8.0],
        "boxes": boxes, "lines": lines,
        "dependency_cache": [{"name": js, "bootpath": ".", "type": "TEXT", "implicit": 1}],
        "latency": 0, "is_mpe": 0, "external_mpe_tuning_enabled": 0,
        "minimum_live_version": "", "minimum_max_version": "", "platform_compatibility": 0,
        "autosave": 0,
    }}


def write(path, p):
    body = json.dumps(p, indent=1).encode() + b"\n\x00"
    data = (b"ampf" + struct.pack("<I", 4) + b"mmmm"          # mmmm = MIDI effect
            + b"meta" + struct.pack("<I", 4) + struct.pack("<I", 0)
            + b"ptch" + struct.pack("<I", len(body)) + body)
    path.write_bytes(data)
    print(f"wrote {path} ({len(data)} bytes)")


def main():
    write(OUT, patcher())
    write(BUILDER, patcher(js="loomback_build.js", buttons=("build", "verify"),
                           status="Send to Ableton in Loomback, then click build (new empty Set recommended)",
                           note="Loomback Builder by SMV — builds tracks, MIDI, warping. Reports: reports/sprint3/"))


if __name__ == "__main__":
    main()
