"""Native Instruments Stems files (.stem.mp4 / .stem.m4a) — e.g. from Traktor.

The format is open: one MP4 holding 5 audio streams that share one timeline.
  stream 0 = full mix, streams 1-4 = stems (NI default order: drums, bass,
  other/"synths", vocals). Stem names live as JSON in an MP4 box called 'stem'
  (moov/udta/stem); we read them when present, else use the default order.
Because the streams share one timeline, extracted stems are sample-aligned
with the mix by construction — no manual lining up in Ableton.
"""
from __future__ import annotations

import json
import re
import struct
import subprocess
from pathlib import Path

from .audio import ffmpeg_path

DEFAULT_NAMES = ["drums", "bass", "other", "vocals"]
NAME_TO_ROLE = [("vocals", r"vocal|vox"), ("drums", r"drum|perc"), ("bass", r"bass"),
                ("melody", r"melod|lead|synth|keys")]


def is_stem_file(path: str | Path) -> bool:
    n = Path(path).name.lower()
    return n.endswith(".stem.mp4") or n.endswith(".stem.m4a")


def _boxes(buf: bytes, start: int, end: int):
    i = start
    while i + 8 <= end:
        size, typ = struct.unpack(">I4s", buf[i:i + 8])
        hdr = 8
        if size == 1:
            size, hdr = struct.unpack(">Q", buf[i + 8:i + 16])[0], 16
        elif size == 0:
            size = end - i
        if size < hdr:
            return
        yield typ.decode("latin1"), i + hdr, i + size
        i += size


def read_metadata(path: str | Path) -> dict | None:
    """The JSON in moov/udta/stem, or None. Reads only the moov box, not the audio."""
    with open(path, "rb") as f:
        data = f.read()
    for typ, s, e in _boxes(data, 0, len(data)):
        if typ != "moov":
            continue
        for t2, s2, e2 in _boxes(data, s, e):
            if t2 != "udta":
                continue
            for t3, s3, e3 in _boxes(data, s2, e2):
                if t3 == "stem":
                    try:
                        return json.loads(data[s3:e3].decode("utf-8").rstrip("\x00"))
                    except ValueError:
                        return None
    return None


def stem_names(path: str | Path) -> list[str]:
    meta = read_metadata(path)
    try:
        names = [s["name"] for s in meta["stems"]]
        if len(names) == 4:
            return names
    except (TypeError, KeyError):
        pass
    return DEFAULT_NAMES


def role_for(name: str) -> str:
    n = name.lower()
    for role, pat in NAME_TO_ROLE:
        if re.search(pat, n):
            return role
    return "other"


def tags(path: str | Path) -> dict:
    """Title / artist etc. from the file's metadata (Traktor names stem files by a
    code like AWQQL5A0V0WGRCBYNBHNCS0WHQFC, so the title must come from inside)."""
    ff = ffmpeg_path()
    if not ff:
        return {}
    err = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    out = {}
    in_meta = False
    for line in err.splitlines():
        if line.strip() == "Metadata:" and not out:
            in_meta = True
            continue
        if in_meta:
            m = re.match(r"\s+(\w+)\s*:\s(.*)", line)
            if not m or line.lstrip().startswith(("Duration", "Stream")):
                break
            out[m.group(1).lower()] = m.group(2).strip()
    return out


def traktor_collections() -> list[Path]:
    """Traktor library files on this Mac, newest first."""
    base = Path.home() / "Documents" / "Native Instruments"
    found = list(base.glob("Traktor*/collection.nml")) if base.is_dir() else []
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


_index_cache: dict[str, dict] | None = None


def traktor_index(nml: Path | None = None) -> dict[str, dict]:
    """Stem-cache code -> {artist, title, file} from Traktor's collection.nml.
    The format is undocumented, so we don't assume where the code is stored:
    any 28-character code appearing anywhere inside a track ENTRY counts."""
    global _index_cache
    if nml is None and _index_cache is not None:
        return _index_cache
    import xml.etree.ElementTree as ET
    out: dict[str, dict] = {}
    for f in ([nml] if nml else traktor_collections()[:1]):
        try:
            for _, el in ET.iterparse(str(f), events=("end",)):
                if el.tag != "ENTRY":
                    continue
                blob = " ".join(" ".join(e.attrib.values()) for e in el.iter())
                loc = el.find("LOCATION")
                info = {"artist": el.get("ARTIST", ""), "title": el.get("TITLE", ""),
                        "file": loc.get("FILE", "") if loc is not None else ""}
                for code in set(re.findall(r"\b[A-Z0-9]{28}\b", blob)):
                    out[code] = info
                el.clear()
        except (ET.ParseError, OSError):
            continue
    if nml is None:
        _index_cache = out
    return out


def display_title(path: str | Path, nml: Path | None = None) -> str:
    """'Artist - Title' from the file's tags, else from Traktor's collection, else the file name."""
    stem = re.sub(r"\.stem\.(mp4|m4a)$", "", Path(path).name, flags=re.I)
    t = tags(path)
    if not t.get("title"):
        t = traktor_index(nml).get(stem, {})
        if not t.get("title") and t.get("file"):
            t = {"title": Path(t["file"]).stem}
    if t.get("title"):
        name = f"{t['artist']} - {t['title']}" if t.get("artist") else t["title"]
        return re.sub(r'[/\\:*?"<>|]', "_", name).strip()
    return stem


def audio_stream_count(path: str | Path) -> int:
    ff = ffmpeg_path()
    if not ff:
        raise RuntimeError("ffmpeg is needed to read .stem.mp4 files (run the Mac installer).")
    err = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    return len(re.findall(r"Stream #0:\d+.*?: Audio:", err))


def extract(path: str | Path, out_dir: str | Path) -> dict[str, Path]:
    """Writes '<title> MIX.wav' and '<title> <name>.wav' (24-bit) into out_dir.
    Returns {role-or-name: path}. File names follow project.scan_folder's rules."""
    path, out_dir = Path(path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = audio_stream_count(path)
    if n != 5:
        raise ValueError(f"{path.name}: expected 5 audio streams (mix + 4 stems), found {n}")
    title = display_title(path)
    names = stem_names(path)
    targets = [("mix", out_dir / f"{title} MIX.wav")]
    for i, name in enumerate(names):
        role = role_for(name)
        label = role if role != "other" else re.sub(r"[^\w -]", "", name).strip() or f"stem{i + 1}"
        targets.append((label, out_dir / f"{title} {label}.wav"))
    cmd = [ffmpeg_path(), "-v", "error", "-y", "-i", str(path)]
    for idx, (_, p) in enumerate(targets):
        cmd += ["-map", f"0:a:{idx}", "-c:a", "pcm_s24le", str(p)]
    subprocess.run(cmd, check=True)
    (out_dir / "stem-source.json").write_text(json.dumps(
        {"from": str(path), "tags": tags(path), "names_in_file": names, "metadata_found": read_metadata(path) is not None}, indent=1))
    return dict(targets)
