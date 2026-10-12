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


def patcher():
    boxes = [
        box("run", "message", "run", [10, 10, 40, 22], ins=2),
        box("verify", "message", "verify", [60, 10, 50, 22], ins=2),
        box("js", "newobj", "js mrs_bridge.js", [10, 45, 120, 22],
            saved_object_attributes={"filename": "mrs_bridge.js", "parameter_enable": 0}),
        box("status", "message", "click run, then save/close/reopen, then verify",
            [10, 80, 400, 22], ins=2),
        box("note", "comment", "MRS Bridge — Sprint 0 test. Results go to reports/sprint0/.",
            [10, 110, 400, 20], outs=0),
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
        "dependency_cache": [{"name": "mrs_bridge.js", "bootpath": ".", "type": "TEXT", "implicit": 1}],
        "latency": 0, "is_mpe": 0, "external_mpe_tuning_enabled": 0,
        "minimum_live_version": "", "minimum_max_version": "", "platform_compatibility": 0,
        "autosave": 0,
    }}


def main():
    body = json.dumps(patcher(), indent=1).encode() + b"\n\x00"
    data = (b"ampf" + struct.pack("<I", 4) + b"mmmm"          # mmmm = MIDI effect
            + b"meta" + struct.pack("<I", 4) + struct.pack("<I", 0)
            + b"ptch" + struct.pack("<I", len(body)) + body)
    OUT.write_bytes(data)
    print(f"wrote {OUT} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
