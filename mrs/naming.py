"""Rename a project, and suggest names from what the files actually say.

Suggestions come only from real sources, each labelled — never invented:
  tags      — title/artist inside the original file (mix or Traktor .stem.mp4)
  traktor   — Traktor's library entry with the same track length
  filename  — the original file / folder name, cleaned up
Traktor cache codes (28 capital letters/digits) are never suggested.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import manifest, nistem

CODE = re.compile(r"^[A-Z0-9]{28}$")
BAD = re.compile(r'[/\\:*?"<>|]')


def clean(name: str) -> str:
    n = re.sub(r"\.(stem\.)?(mp4|m4a|wav|aiff?|flac|mp3)$", "", name, flags=re.I)
    n = re.sub(r"[_]+", " ", n)
    n = re.sub(r"\b(MIX|master|full mix|mixdown)\b", "", n, flags=re.I)
    n = re.sub(r"\s*\((stems|MRS)\)\s*$", "", n, flags=re.I)
    return re.sub(r"\s{2,}", " ", n).strip(" -")


def suggest(pdir: str | Path) -> list[dict]:
    pdir = Path(pdir)
    m = manifest.load(pdir / "project.json")
    files = [Path(manifest.mix(m)["path"])]
    origin = pdir / "stems" / "stem-source.json"
    if origin.exists():
        files.insert(0, Path(json.loads(origin.read_text())["from"]))
    out, seen = [], set()

    def add(name, source):
        name = BAD.sub("_", (name or "").strip())
        if name and not CODE.match(name) and name.lower() not in seen:
            seen.add(name.lower())
            out.append({"name": name, "source": source})

    for f in files:
        if not f.exists():
            continue
        t = nistem.tags(f)
        if t.get("title"):
            add(f"{t['artist']} - {t['title']}" if t.get("artist") else t["title"], f"tags in {f.name}")
            add(t["title"], f"title tag in {f.name}")
        if nistem.is_stem_file(f):
            hit = nistem.traktor_index().get(f.name[:-9]) or nistem.match_by_length(f)
            if hit.get("title"):
                add(f"{hit['artist']} - {hit['title']}" if hit.get("artist") else hit["title"], "Traktor library (same length)")
        add(clean(f.name), "file name")
        add(clean(f.parent.name), "folder name")
    return out


def rename(pdir: str | Path, new_name: str) -> Path:
    """Sets the project's name and renames its folder; source paths inside the
    folder are rewritten so nothing breaks. Files outside it are untouched."""
    pdir = Path(pdir).resolve()
    new_name = BAD.sub("_", new_name.strip())
    if not new_name:
        raise ValueError("empty name")
    m = manifest.load(pdir / "project.json")
    m["name"] = new_name
    target = pdir.with_name(new_name)
    if target != pdir:
        if target.exists():
            raise FileExistsError(f"a project called '{new_name}' already exists")
        old = str(pdir)
        for s in m["sources"]:
            if s["path"].startswith(old + "/"):
                s["path"] = str(target) + s["path"][len(old):]
        shutil.move(str(pdir), str(target))
    manifest.save(m, target / "project.json")
    return target
