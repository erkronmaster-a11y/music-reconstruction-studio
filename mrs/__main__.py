"""Command line.

  python -m mrs analyze <song folder | file.stem.mp4> [--out <project folder>]
  python -m mrs info    <project.json>
  python -m mrs tempo   <project.json> [--bpm 120] [--downbeat 0.52] [--bar 4] [--clear]
  python -m mrs click   <project.json>           # writes click-check.wav next to it
"""
import argparse
import sys
import time
from pathlib import Path

import re

from . import manifest, nistem, project


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mrs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze"); a.add_argument("folder"); a.add_argument("--out")
    a.add_argument("--out-parent", help="put the project in <this>/<song title>/")
    i = sub.add_parser("info"); i.add_argument("project")
    t = sub.add_parser("tempo"); t.add_argument("project")
    t.add_argument("--bpm", type=float); t.add_argument("--downbeat", type=float)
    t.add_argument("--bar", type=int); t.add_argument("--note"); t.add_argument("--clear", action="store_true")
    c = sub.add_parser("click"); c.add_argument("project")
    tl = sub.add_parser("traktor-list", help="list Traktor's cached stem files with song titles")
    tl.add_argument("--dir", default=str(Path.home() / "Music" / "Traktor" / "Stems"))
    args = ap.parse_args(argv)

    if args.cmd == "analyze":
        folder = Path(args.folder)
        if nistem.is_stem_file(folder):  # Traktor / NI Stems: unpack first, perfectly aligned
            src = folder
            title = nistem.display_title(src)
            out = Path(args.out) if args.out else src.with_name(title + " (MRS)")
            if args.out_parent:
                out = Path(args.out_parent) / title
            folder = out / "stems"
            name = title
            nistem.extract(src, folder)
            print(f"Unpacked {src.name} into {folder}")
        else:
            out = Path(args.out) if args.out else folder / "mrs-project"
            if args.out_parent:
                out = Path(args.out_parent) / folder.name
            name = folder.name
        out.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        m, _ = project.build(folder=folder, name=name)
        m["analysis_seconds"] = round(time.time() - t0, 1)
        manifest.save(m, out / "project.json")
        (out / "summary.txt").write_text(project.summary(m) + "\n")
        print(project.summary(m))
        print(f"\nSaved {out / 'project.json'}  ({m['analysis_seconds']} s)")
        print(f"PROJECT_DIR={out}")
    elif args.cmd == "info":
        print(project.summary(manifest.load(args.project)))
    elif args.cmd == "tempo":
        m = manifest.load(args.project)
        if args.clear:
            manifest.clear_timing_correction(m)
        else:
            manifest.correct_timing(m, args.bpm, args.downbeat, args.bar, args.note)
        manifest.save(m, args.project)
        print(project.summary(m))
    elif args.cmd == "traktor-list":
        files = sorted(Path(args.dir).rglob("*.stem.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        idx = nistem.traktor_index()
        nml = nistem.traktor_collections()
        print(f"{len(files)} stem files in {args.dir}; library: {nml[0] if nml else 'collection.nml not found'}")
        print(f"titles matched from library: {sum(1 for f in files if f.name[:-9] in idx)}")
        for f in files:
            print(f"{time.strftime('%Y-%m-%d', time.localtime(f.stat().st_mtime))}  {nistem.display_title(f):60.60}  {f}")
    elif args.cmd == "click":
        m = manifest.load(args.project)
        out = project.render_click(m, Path(args.project).with_name("click-check.wav"))
        print(f"Wrote {out} — listen: high click = bar start, low click = beat.")


if __name__ == "__main__":
    sys.exit(main())
