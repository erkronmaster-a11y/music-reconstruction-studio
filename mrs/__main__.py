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
    i = sub.add_parser("info"); i.add_argument("project")
    t = sub.add_parser("tempo"); t.add_argument("project")
    t.add_argument("--bpm", type=float); t.add_argument("--downbeat", type=float)
    t.add_argument("--bar", type=int); t.add_argument("--note"); t.add_argument("--clear", action="store_true")
    c = sub.add_parser("click"); c.add_argument("project")
    args = ap.parse_args(argv)

    if args.cmd == "analyze":
        folder = Path(args.folder)
        if nistem.is_stem_file(folder):  # Traktor / NI Stems: unpack first, perfectly aligned
            src = folder
            title = re.sub(r"\.stem\.(mp4|m4a)$", "", src.name, flags=re.I)
            out = Path(args.out) if args.out else src.with_name(title + " (MRS)")
            folder = out / "stems"
            name = title
            nistem.extract(src, folder)
            print(f"Unpacked {src.name} into {folder}")
        else:
            out = Path(args.out) if args.out else folder / "mrs-project"
            name = folder.name
        out.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        m, _ = project.build(folder=folder, name=name)
        m["analysis_seconds"] = round(time.time() - t0, 1)
        manifest.save(m, out / "project.json")
        (out / "summary.txt").write_text(project.summary(m) + "\n")
        print(project.summary(m))
        print(f"\nSaved {out / 'project.json'}  ({m['analysis_seconds']} s)")
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
    elif args.cmd == "click":
        m = manifest.load(args.project)
        out = project.render_click(m, Path(args.project).with_name("click-check.wav"))
        print(f"Wrote {out} — listen: high click = bar start, low click = beat.")


if __name__ == "__main__":
    sys.exit(main())
