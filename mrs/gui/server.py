"""Loomback — local GUI for the reconstruction pipeline (by SMV).

A small web server on 127.0.0.1 only; the page talks to it with JSON. Every
pipeline step runs as `python -m mrs …` in a subprocess, so the GUI shows the
same output the command line does and a crash never takes the GUI down.
Nothing leaves the machine.

  python -m mrs.gui.server            → http://127.0.0.1:8765
"""
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

STATIC = Path(__file__).parent / "static"
PROJECTS = Path(os.environ.get("MRS_PROJECTS", Path.home() / "Music" / "MRS Projects"))
INBOX = PROJECTS / "_inbox"
TRAKTOR = Path.home() / "Music" / "Traktor" / "Stems"
TRAKTOR_CACHE = PROJECTS / "_traktor_titles.json"
AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a"}
JOBS: dict[str, dict] = {}


def allowed(p: Path) -> bool:
    """Only files inside the projects folder, the Traktor stem cache, or a path
    the user explicitly handed to a job may be read."""
    p = p.resolve()
    roots = [PROJECTS.resolve(), TRAKTOR.resolve()] + [Path(j["src"]).resolve() for j in JOBS.values() if j.get("src")]
    return any(p == r or r in p.parents for r in roots)


def project_source(p: Path) -> bool:
    """Audio a project points to may live outside the projects folder (a song
    analysed from its own folder). Those exact files may be played."""
    p = p.resolve()
    for pj in PROJECTS.glob("*/project.json"):
        try:
            if any(Path(s["path"]).resolve() == p for s in json.loads(pj.read_text())["sources"]):
                return True
        except (ValueError, KeyError):
            continue
    return False


# ---------- jobs ----------
def run_job(args: list[str], src: str | None = None) -> str:
    jid = uuid.uuid4().hex[:8]
    job = {"id": jid, "args": args, "src": src, "log": [], "state": "running", "started": time.time(), "result": None}
    JOBS[jid] = job

    def work():
        cmd = [sys.executable, "-W", "ignore", "-u", "-m", "mrs"] + args
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 cwd=Path(__file__).resolve().parents[2])
            for line in p.stdout:
                line = line.rstrip()
                if line:
                    job["log"].append(line)
                    if line.startswith("PROJECT_DIR="):
                        job["result"] = line.split("=", 1)[1]
            job["state"] = "done" if p.wait() == 0 else "failed"
        except Exception as e:  # report, never hide
            job["log"].append(f"ERROR: {e!r}")
            job["state"] = "failed"
        job["seconds"] = round(time.time() - job["started"], 1)
    threading.Thread(target=work, daemon=True).start()
    return jid


def list_projects() -> list[dict]:
    out = []
    for pj in sorted(PROJECTS.glob("*/project.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            m = json.loads(pj.read_text())
        except ValueError:
            continue
        d = m["timing"].get("detected") or {}
        out.append({"name": m["name"], "dir": str(pj.parent), "tracks": [t["id"] for t in m.get("tracks", [])],
                    "tempo": d.get("tempo_bpm"), "mode": d.get("export_mode"),
                    "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(pj.stat().st_mtime))})
    return out


def traktor_list(refresh: bool = False) -> dict:
    """Titles take ~1 ffmpeg call per file, so they are cached on disk."""
    cache = {}
    if TRAKTOR_CACHE.exists() and not refresh:
        cache = json.loads(TRAKTOR_CACHE.read_text())
    from mrs import nistem
    files = sorted(TRAKTOR.rglob("*.stem.mp4"), key=lambda p: p.stat().st_mtime, reverse=True) if TRAKTOR.is_dir() else []
    changed = False
    items = []
    for f in files:
        key = f.name
        if key not in cache:
            cache[key] = nistem.display_title(f)
            changed = True
        items.append({"path": str(f), "title": cache[key], "titled": cache[key] != f.name[:-9],
                      "date": time.strftime("%Y-%m-%d", time.localtime(f.stat().st_mtime))})
    if changed:
        PROJECTS.mkdir(parents=True, exist_ok=True)
        TRAKTOR_CACHE.write_text(json.dumps(cache))
    return {"folder": str(TRAKTOR), "items": items}


def load_project(d: str) -> dict:
    pdir = Path(d)
    if not allowed(pdir / "project.json"):
        raise PermissionError(d)
    from mrs import manifest
    m = manifest.load(pdir / "project.json")
    out = {"dir": d, "project": m}
    for t in m.get("tracks", []):
        t["notes_view"] = manifest.effective_notes(t, "raw")  # GUI shows all, dims flagged ones
    ex = pdir / "midi" / "export.json"
    if ex.exists():
        out["export"] = json.loads(ex.read_text())
    rv = pdir / "review" / "review.json"
    if rv.exists():
        out["review"] = json.loads(rv.read_text())
    return out


# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/projects":
                return self.send(200, list_projects())
            if u.path == "/api/project":
                return self.send(200, load_project(q["dir"]))
            if u.path == "/api/traktor":
                return self.send(200, traktor_list(q.get("refresh") == "1"))
            if u.path == "/api/names":
                if not allowed(Path(q["dir"]) / "project.json"):
                    return self.send(403, {"error": "not allowed"})
                from mrs import naming
                return self.send(200, naming.suggest(q["dir"]))
            if u.path == "/api/job":
                j = JOBS.get(q["id"])
                return self.send(200 if j else 404, j or {"error": "no such job"})
            if u.path == "/api/audio":
                p = Path(q["path"])
                if not ((allowed(p) or project_source(p)) and p.suffix.lower() in AUDIO_EXT and p.is_file()):
                    return self.send(403, {"error": "not allowed"})
                return self.send(200, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "application/octet-stream")
            f = (STATIC / (u.path.lstrip("/") or "index.html")).resolve()
            if STATIC.resolve() in f.parents and f.is_file():
                return self.send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            return self.send(404, {"error": "not found"})
        except (KeyError, PermissionError, ValueError, FileNotFoundError) as e:
            return self.send(400, {"error": repr(e)})

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        try:
            if u.path == "/api/upload":  # raw file body; name in header
                name = Path(self.headers.get("X-Filename", "upload.wav")).name
                dest = INBOX / time.strftime("%Y%m%d-%H%M%S")
                dest.mkdir(parents=True, exist_ok=True)
                remaining = n
                with open(dest / name, "wb") as f:
                    while remaining:
                        chunk = self.rfile.read(min(1 << 20, remaining))
                        if not chunk:
                            break
                        f.write(chunk)
                        remaining -= len(chunk)
                return self.send(200, {"path": str(dest / name), "folder": str(dest)})
            body = json.loads(self.rfile.read(n) or b"{}")
            if u.path == "/api/run":
                a = body["action"]
                if a == "analyze":
                    src = body["src"]
                    return self.send(200, {"job": run_job(["analyze", src, "--out-parent", str(PROJECTS)], src)})
                pj = str(Path(body["dir"]) / "project.json")
                if not allowed(Path(pj)):
                    return self.send(403, {"error": "not allowed"})
                args = {"transcribe": ["transcribe", pj],
                        "export": ["export", pj],
                        "click": ["click", pj],
                        "redetect": ["tempo", pj, "--redetect"],
                        "clear": ["tempo", pj, "--clear"]}.get(a)
                if a == "tempo":
                    args = ["tempo", pj]
                    for k, flag in (("bpm", "--bpm"), ("downbeat", "--downbeat")):
                        if body.get(k) not in (None, ""):
                            args += [flag, str(float(body[k]))]
                if a == "live":
                    args = ["live-plan", pj]
                if a == "rename":
                    args = ["rename", pj, str(body["name"])]
                if a == "all":
                    args = ["pipeline", pj]
                if not args:
                    return self.send(400, {"error": f"unknown action {a}"})
                return self.send(200, {"job": run_job(args)})
            if u.path == "/api/open":
                p = Path(body["path"])
                if allowed(p) and sys.platform == "darwin":
                    subprocess.Popen(["open", str(p)])
                return self.send(200, {"ok": True})
            return self.send(404, {"error": "not found"})
        except (KeyError, ValueError) as e:
            return self.send(400, {"error": repr(e)})


def main(port: int = 8765, open_browser: bool = True):
    PROJECTS.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Loomback running at {url}  (close this window to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    srv.serve_forever()


if __name__ == "__main__":
    main(int(os.environ.get("LOOMBACK_PORT", 8765)), os.environ.get("LOOMBACK_NO_BROWSER") != "1")
