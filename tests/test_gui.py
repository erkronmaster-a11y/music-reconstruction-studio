"""Loomback server: endpoints answer, and audio access is limited to project files."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from mrs import project, manifest, testsong


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp("gui")
    src = root / "src" / "Night Drive"
    testsong.make(src, bars=4)
    m, _ = project.build(folder=src, name="Night Drive")
    (root / "projects" / "Night Drive").mkdir(parents=True)
    manifest.save(m, root / "projects" / "Night Drive" / "project.json")
    from mrs.gui import server as srv
    srv.PROJECTS = root / "projects"
    httpd = srv.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", root
    httpd.shutdown()


def get(url):
    with urllib.request.urlopen(url) as r:
        return r.status, r.read()


def test_page_and_projects(server):
    base, root = server
    assert b"Loomback" in get(base + "/")[1]
    projects = json.loads(get(base + "/api/projects")[1])
    assert projects[0]["name"] == "Night Drive" and projects[0]["mode"] in ("constant", "beatmap")
    p = json.loads(get(base + "/api/project?dir=" + urllib.request.quote(projects[0]["dir"]))[1])
    assert p["project"]["timing"]["detected"]["beat_map"]["beats_s"]


def test_audio_only_for_project_sources(server, tmp_path):
    base, root = server
    mix = root / "src" / "Night Drive" / "Test Song MIX.wav"   # outside projects/, but a project source
    assert get(base + "/api/audio?path=" + urllib.request.quote(str(mix)))[0] == 200
    other = tmp_path / "secret.wav"
    other.write_bytes(mix.read_bytes())
    with pytest.raises(urllib.error.HTTPError) as e:
        get(base + "/api/audio?path=" + urllib.request.quote(str(other)))
    assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError):
        get(base + "/../../etc/passwd")
