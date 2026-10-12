// Loomback Builder — builds the arrangement from <repo>/live/inbox/build.json
// (written by Loomback's "Send to Ableton" or `python -m mrs live-plan`).
//
//   build  -> tempo, audio tracks (warped by markers), MIDI tracks + notes,
//             names, colours, mutes, a native instrument where possible
//   verify -> reads the Set back and compares it with the plan
//
// Only Live Object Model calls verified on Live 12.0.15 in Sprint 0, or
// documented ones whose result is read back and reported:
//   create_audio_track / create_audio_clip, create_midi_track,
//   ClipSlot.create_clip + add_new_notes + Track.duplicate_clip_to_arrangement,
//   Clip warping / warp_mode / add_warp_marker / move_warp_marker / remove_warp_marker,
//   Browser + load_item (instruments; best effort).
// Results: <repo>/reports/sprint3/live-build.json and live-verify.json.

autowatch = 1;
inlets = 1;
outlets = 1;

var R;           // report

function show(m) { outlet(0, "set", m); }
function step(name, ok, detail) {
    R.steps.push({ step: name, ok: !!ok, detail: detail === undefined ? null : detail });
    post("LB " + (ok ? "OK   " : "FAIL ") + name + (detail !== undefined ? " :: " + JSON.stringify(detail).substring(0, 300) : "") + "\n");
    return ok;
}

// ---------- files ----------
function repoDir() {
    var p = String(this.patcher.filepath || "");
    var i = p.lastIndexOf("/live/");
    if (i < 0) return null;
    return p.substring(0, i);
}
function posix(p) { return String(p).replace(/^[^\/]*:/, ""); }

function readText(path) {
    var f = new File(path, "read");
    if (!f.isopen) return null;
    var s = "", chunk;
    while (f.position < f.eof) {
        chunk = f.readstring(16000);
        if (!chunk) break;
        s += chunk;
    }
    f.close();
    return s;
}
function fileSize(path) { var f = new File(path, "read"); if (!f.isopen) return 0; var n = f.eof; f.close(); return n; }
function writeJson(name, obj) {
    var dir = repoDir(); if (!dir) return null;
    var s = JSON.stringify(obj, null, 1);
    var paths = [dir + "/reports/sprint3/" + name, posix(dir) + "/reports/sprint3/" + name];
    for (var i = 0; i < paths.length; i++) {
        try { var d = new Dict(); d.parse(s); d.export_json(paths[i]); } catch (e) {}
        if (fileSize(paths[i]) > 0) return paths[i];
        var f = new File(paths[i], "write", "TEXT");
        if (f.isopen) { for (var k = 0; k < s.length; k += 2000) f.writestring(s.substring(k, k + 2000)); f.eof = f.position; f.close(); }
        if (fileSize(paths[i]) > 0) return paths[i];
    }
    return null;
}

// ---------- LOM helpers ----------
function ids(api, prop) {
    var raw = api.get(prop), out = [];
    if (!raw) return out;
    for (var i = 0; i < raw.length; i++) if (raw[i] === "id" && raw[i + 1] !== 0) out.push(raw[i + 1]);
    return out;
}
function parseDict(ret) {
    if (ret === undefined || ret === null) return null;
    var s = (ret instanceof Array) ? ret.join(" ") : String(ret);
    try { return JSON.parse(s); } catch (e) { return null; }
}
function markers(clip) {
    var d = parseDict(clip.get("warp_markers"));
    return d && d.warp_markers ? d.warp_markers : [];
}
function findTrack(song, name) {
    var n = song.getcount("tracks");
    for (var i = 0; i < n; i++) {
        var t = new LiveAPI("live_set tracks " + i);
        if (String(t.get("name")) === name) return i;
    }
    return -1;
}

// ---------- build ----------
function build() {
    R = { phase: "build", time: new Date().toString(), live_version: null, steps: [], tracks: [] };
    var app = new LiveAPI("live_app");
    R.live_version = app.call("get_major_version") + "." + app.call("get_minor_version") + "." + app.call("get_bugfix_version");
    var dir = repoDir();
    var txt = dir ? readText(dir + "/live/inbox/build.json") : null;
    var plan = null;
    try { plan = JSON.parse(txt); } catch (e) {}
    if (!step("read plan (live/inbox/build.json)", plan && plan.format === "loomback-live-plan",
              plan ? { project: plan.project, tracks: plan.tracks.length } : "missing — click 'Send to Ableton' in Loomback first")) {
        return finish("live-build.json");
    }
    R.project = plan.project;
    show("building " + plan.project + " …");
    var song = new LiveAPI("live_set");
    song.set("tempo", plan.tempo_bpm);
    step("tempo", Math.abs(Number(song.get("tempo")) - plan.tempo_bpm) < 0.001, Number(song.get("tempo")));
    song.set("signature_numerator", plan.beats_per_bar);
    song.set("signature_denominator", 4);

    for (var i = 0; i < plan.tracks.length; i++) {
        var t = plan.tracks[i];
        var res = { name: t.name, kind: t.kind };
        try {
            var old = findTrack(song, t.name);           // re-running replaces the earlier build
            if (old >= 0) song.call("delete_track", old);
            if (t.kind === "audio") buildAudio(song, t, res); else buildMidi(song, t, res, plan);
        } catch (e) { res.error = String(e); }
        R.tracks.push(res);
        step("track: " + t.name, !res.error, res);
    }
    finish("live-build.json");
}

function newTrack(song, kind, t) {
    var before = song.getcount("tracks");
    song.call(kind === "audio" ? "create_audio_track" : "create_midi_track", -1);
    var idx = song.getcount("tracks") - 1;
    if (idx !== before) throw "could not create " + kind + " track";
    var tr = new LiveAPI("live_set tracks " + idx);
    tr.set("name", t.name);
    tr.set("color", t.color);
    if (t.mute) tr.set("mute", 1);
    return { api: tr, index: idx };
}

function buildAudio(song, t, res) {
    var tr = newTrack(song, "audio", t);
    tr.api.call("create_audio_clip", posix(t.file), 0.0);
    var cids = ids(tr.api, "arrangement_clips");
    if (cids.length !== 1) throw "create_audio_clip made no clip for " + t.file;
    var clip = new LiveAPI("id " + cids[0]);
    clip.set("warping", 1);
    var modes = clip.get("available_warp_modes") || [];
    var wantMode = t.warp_mode;
    var hasMode = false;
    for (var k = 0; k < modes.length; k++) if (Number(modes[k]) === wantMode) hasMode = true;
    clip.set("warp_mode", hasMode ? wantMode : 4);   // Complex Pro, else Complex
    res.warp_mode = Number(clip.get("warp_mode"));

    // Markers: keep Live's first and last, delete any others, move those two to
    // our first/last positions (so every stretch has a realistic tempo — Live
    // only accepts 5–999 BPM between markers), then add ours in between.
    var ex = markers(clip);
    res.markers_before = ex.length;
    for (var j = ex.length - 2; j >= 1; j--) clip.call("remove_warp_marker", ex[j].beat_time);
    ex = markers(clip);
    var want = t.warp_markers;
    var first = want[0], last = want[want.length - 1];
    if (ex.length >= 2) {
        clip.call("move_warp_marker", ex[0].beat_time, first.beat_time - ex[0].beat_time);
        ex = markers(clip);
        clip.call("move_warp_marker", ex[ex.length - 1].beat_time, last.beat_time - ex[ex.length - 1].beat_time);
    } else {
        clip.call("add_warp_marker", { beat_time: first.beat_time, sample_time: first.sample_time });
        clip.call("add_warp_marker", { beat_time: last.beat_time, sample_time: last.sample_time });
    }
    for (var m = 1; m < want.length - 1; m++) {
        clip.call("add_warp_marker", { beat_time: want[m].beat_time, sample_time: want[m].sample_time });
    }
    // clip length follows the audio
    try { clip.set("end_marker", last.beat_time); clip.set("loop_end", last.beat_time); } catch (e) {}
    var fin = markers(clip);
    res.markers_wanted = want.length;
    res.markers_now = fin.length;
    res.first_marker = fin[0];
    res.last_marker = fin[fin.length - 1];
    res.clip_start = Number(clip.get("start_time"));
    res.clip_end = Number(clip.get("end_time"));
    // check: every wanted marker present within 1 ms / 0.001 beat
    var miss = 0;
    for (var w = 0; w < want.length; w++) {
        var found = false;
        for (var f = 0; f < fin.length && !found; f++)
            if (Math.abs(fin[f].beat_time - want[w].beat_time) < 0.001 && Math.abs(fin[f].sample_time - want[w].sample_time) < 0.001) found = true;
        if (!found) miss++;
    }
    res.markers_missing = miss;
    if (miss > 0) res.error = miss + " of " + want.length + " warp markers did not land";
}

function buildMidi(song, t, res, plan) {
    var tr = newTrack(song, "midi", t);
    var slot = new LiveAPI("live_set tracks " + tr.index + " clip_slots 0");
    slot.call("create_clip", plan.length_beats);
    var sc = new LiveAPI("live_set tracks " + tr.index + " clip_slots 0 clip");
    if (!sc.id || sc.id == 0) throw "session clip not created";
    sc.set("name", t.name + " (raw)");
    for (var k = 0; k < t.notes.length; k += 400) {
        var chunk = t.notes.slice(k, k + 400);
        sc.call("add_new_notes", { notes: chunk });
    }
    var got = parseDict(sc.call("get_notes_extended", 0, 128, 0.0, plan.length_beats + 4));
    res.notes_wanted = t.notes.length;
    res.notes_in_clip = got && got.notes ? got.notes.length : 0;
    tr.api.call("duplicate_clip_to_arrangement", "id", Number(sc.id), 0.0);
    var cids = ids(tr.api, "arrangement_clips");
    if (cids.length !== 1) throw "duplicate_clip_to_arrangement made no clip";
    slot.call("delete_clip");
    var ac = new LiveAPI("id " + cids[0]);
    var back = parseDict(ac.call("get_notes_extended", 0, 128, 0.0, plan.length_beats + 4));
    res.notes_in_arrangement = back && back.notes ? back.notes.length : 0;
    if (res.notes_in_arrangement !== t.notes.length) res.error = "note count " + res.notes_in_arrangement + " ≠ " + t.notes.length;
    res.instrument = loadInstrument(song, tr, t.instrument_candidates || []);
}

// Best effort: Live's browser, documented in the LOM. Selects the track, then
// loads the first browser item whose name matches a candidate.
function loadInstrument(song, tr, names) {
    if (!names.length) return null;
    try {
        var br = new LiveAPI("live_app browser");
        var view = new LiveAPI("live_set view");
        view.set("selected_track", "id", Number(tr.api.id));
        var roots = ["instruments", "drums"];
        for (var n = 0; n < names.length; n++) {
            for (var r = 0; r < roots.length; r++) {
                var hit = searchBrowser(new LiveAPI("live_app browser " + roots[r]), names[n], 2);
                if (hit) {
                    br.call("load_item", "id", Number(hit.id));
                    var devs = ids(tr.api, "devices");
                    return { loaded: devs.length > 0, item: String(hit.get("name")), root: roots[r] };
                }
            }
        }
        return { loaded: false, note: "none of " + names.join(", ") + " found in the browser" };
    } catch (e) { return { loaded: false, error: String(e) }; }
}
function searchBrowser(item, name, depth) {
    var kids = ids(item, "children");
    for (var i = 0; i < kids.length; i++) {
        var c = new LiveAPI("id " + kids[i]);
        var nm = String(c.get("name")).replace(/\.(adg|adv)$/, "");
        if (nm === name && Number(c.get("is_loadable")) === 1) return c;
    }
    if (depth > 0) for (var j = 0; j < kids.length; j++) {
        var cc = new LiveAPI("id " + kids[j]);
        if (Number(cc.get("is_folder")) === 1) { var h = searchBrowser(cc, name, depth - 1); if (h) return h; }
    }
    return null;
}

// ---------- verify ----------
function verify() {
    R = { phase: "verify", time: new Date().toString(), steps: [] };
    var dir = repoDir();
    var plan = null;
    try { plan = JSON.parse(readText(dir + "/live/inbox/build.json")); } catch (e) {}
    if (!step("read plan", !!plan)) return finish("live-verify.json");
    var song = new LiveAPI("live_set");
    step("tempo", Math.abs(Number(song.get("tempo")) - plan.tempo_bpm) < 0.001, Number(song.get("tempo")));
    for (var i = 0; i < plan.tracks.length; i++) {
        var t = plan.tracks[i], idx = findTrack(song, t.name);
        if (!step("present: " + t.name, idx >= 0)) continue;
        var tr = new LiveAPI("live_set tracks " + idx), cids = ids(tr, "arrangement_clips");
        if (!step("clip: " + t.name, cids.length === 1, cids.length)) continue;
        var clip = new LiveAPI("id " + cids[0]);
        if (t.kind === "midi") {
            var got = parseDict(clip.call("get_notes_extended", 0, 128, 0.0, plan.length_beats + 4));
            var notes = got && got.notes ? got.notes : [];
            notes.sort(function (a, b) { return a.start_time - b.start_time || a.pitch - b.pitch; });
            var want = t.notes.slice().sort(function (a, b) { return a.start_time - b.start_time || a.pitch - b.pitch; });
            var bad = 0;
            for (var k = 0; k < Math.min(notes.length, want.length); k++)
                if (notes[k].pitch !== want[k].pitch || Math.abs(notes[k].start_time - want[k].start_time) > 0.001) bad++;
            step("notes: " + t.name, notes.length === want.length && bad === 0, { found: notes.length, wanted: want.length, mismatched: bad });
        } else {
            var mk = markers(clip);
            step("warp: " + t.name, Number(clip.get("warping")) === 1 && mk.length >= t.warp_markers.length,
                 { markers: mk.length, wanted: t.warp_markers.length, mode: Number(clip.get("warp_mode")) });
        }
    }
    finish("live-verify.json");
}

function finish(file) {
    var failed = [];
    for (var i = 0; i < R.steps.length; i++) if (!R.steps[i].ok) failed.push(R.steps[i].step);
    R.summary = failed.length ? "FAILED: " + failed.join(" | ") : "ALL OK";
    var saved = writeJson(file, R);
    show(R.phase + " — " + R.summary + (saved ? " — report saved" : " — REPORT NOT SAVED"));
}

function bang() { build(); }
