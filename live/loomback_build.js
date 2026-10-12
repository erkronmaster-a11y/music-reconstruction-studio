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
// Plan and reports go through ~/Music/MRS Projects/_live/ (fixed, works
// wherever Live keeps the device), with <repo>/live/inbox and
// <repo>/reports/sprint3 as second choices.

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
// Mac test: Live loaded the device from somewhere other than <repo>/live/, so
// repoDir() was null and both the plan and the report were "missing". The
// fixed exchange folder ~/Music/MRS Projects/_live/ does not depend on where
// the device file sits; home is taken from any /Users/<name>/ path.
function homeDir() {
    var p = posix(String(this.patcher.filepath || ""));
    var m = p.match(/^(\/Users\/[^\/]+)\//);
    return m ? m[1] : null;
}
function exchangeDirs() {
    var out = [], h = homeDir(), r = repoDir();
    if (h) out.push(h + "/Music/MRS Projects/_live");
    if (r) { out.push(posix(r) + "/live/inbox"); }
    out.push("/tmp/loomback");   // last resort: needs no knowledge of any path
    return out;
}
function readPlan() {
    var dirs = exchangeDirs(), tried = [];
    for (var i = 0; i < dirs.length; i++) {
        var path = dirs[i] + "/build.json";
        tried.push(path);
        var txt = readText(path);
        if (txt) {
            try { return { plan: JSON.parse(txt), path: path }; }
            catch (e) { return { error: "plan unreadable: " + e, path: path }; }
        }
    }
    return { error: "no plan found — click 'Send to Ableton' in Loomback first", tried: tried,
             device_path: String(this.patcher.filepath || "(unknown)") };
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
// Max's File/Dict writers failed on non-ASCII text ("—", "≠") on the Mac:
// the report was "NOT SAVED". Everything above 0x7F is written as \uXXXX,
// which is still valid JSON.
function ascii(s) {
    return s.replace(/[\u0080-\uffff]/g, function (c) { return "\\u" + ("0000" + c.charCodeAt(0).toString(16)).slice(-4); });
}
function writeJson(name, obj) {
    var s = ascii(JSON.stringify(obj, null, 1));
    var paths = [], h = homeDir(), dir = repoDir();
    if (h) paths.push(h + "/Music/MRS Projects/_live/" + name);   // collected by 7-send-ableton-results
    if (dir) paths.push(posix(dir) + "/reports/sprint3/" + name, posix(dir) + "/reports/" + name);
    paths.push("/tmp/loomback/" + name);
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
    var rp = readPlan(), plan = rp.plan;
    if (!step("read plan", plan && plan.format === "loomback-live-plan",
              plan ? { project: plan.project, tracks: plan.tracks.length, from: rp.path } : rp)) {
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

    // Warp markers. Mac run (Live 12.0.15): Live's dict holds the first marker
    // plus a hidden helper ~0.03 beat after it (it sets the clip tempo), and
    // add_warp_marker with an explicit sample_time was refused for all 257
    // markers past that helper — a new marker must lie BETWEEN two existing
    // ones. So: (1) move the first marker to our first, (2) create our END
    // marker the documented way — add with beat_time only (Live picks the
    // sample) and move it to our end beat — (3) add the rest, which now all
    // fall between two markers.
    var ex = markers(clip);
    res.markers_before = ex.length;
    res.live_markers_at_start = ex;
    var want = t.warp_markers;
    var first = want[0], last = want[want.length - 1];
    if (ex.length) clip.call("move_warp_marker", ex[0].beat_time, first.beat_time - ex[0].beat_time);
    res.end_marker = placeAtSample(clip, last.sample_time, last.beat_time);
    var refused = 0;
    for (var m = 1; m < want.length - 1; m++) {
        var n0 = markers(clip).length;
        clip.call("add_warp_marker", { beat_time: want[m].beat_time, sample_time: want[m].sample_time });
        if (markers(clip).length === n0) {          // refused: fall back to add-then-move
            refused++;
            placeAtSample(clip, want[m].sample_time, want[m].beat_time);
        }
    }
    res.explicit_adds_refused = refused;
    // Live's hidden tempo helper (moved along with the first marker) is now a
    // stray marker just after our first one: remove anything that is not ours.
    var now = markers(clip), strays = 0;
    for (var q = now.length - 2; q >= 1; q--) {
        var mine = false;
        for (var w2 = 0; w2 < want.length && !mine; w2++)
            if (Math.abs(now[q].beat_time - want[w2].beat_time) < 0.001) mine = true;
        if (!mine) { clip.call("remove_warp_marker", now[q].beat_time); strays++; }
    }
    res.stray_markers_removed = strays;
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
            if (Math.abs(fin[f].beat_time - want[w].beat_time) < 0.001 && Math.abs(fin[f].sample_time - want[w].sample_time) < 0.003) found = true;
        if (!found) miss++;
    }
    res.markers_missing = miss;
    if (miss > 0) res.error = miss + " of " + want.length + " warp markers did not land";
}

// Put a marker at sample time S and beat B without giving Live a sample_time:
// find the beat where S currently plays (from the existing markers), add a
// marker there, then move it to B. Returns what Live ended up with.
function placeAtSample(clip, S, B) {
    var mk = markers(clip);
    if (!mk.length) return { error: "no markers" };
    var a = mk[0], b2 = mk[mk.length - 1];
    for (var i = 0; i < mk.length - 1; i++) if (mk[i].sample_time <= S) { a = mk[i]; b2 = mk[i + 1]; }
    var slope = (b2.beat_time - a.beat_time) / Math.max(1e-9, b2.sample_time - a.sample_time);
    var b0 = a.beat_time + (S - a.sample_time) * slope;
    clip.call("add_warp_marker", { beat_time: b0 });
    clip.call("move_warp_marker", b0, B - b0);
    var after = markers(clip), best = null;
    for (var k = 0; k < after.length; k++) if (!best || Math.abs(after[k].beat_time - B) < Math.abs(best.beat_time - B)) best = after[k];
    return { asked: { beat_time: B, sample_time: S }, got: best };
}

// Instruments: if the Set has a template track "LB Bass" / "LB Melody" /
// "LB Drums" (any instrument or VST on it), it is duplicated for this part —
// the owner's preselected sounds. Otherwise an empty MIDI track, then a
// best-effort browser load (found nothing on Live 12.0.15).
function templateIndex(song, role) {
    var want = "lb " + role, n = song.getcount("tracks");
    for (var i = 0; i < n; i++) {
        var nm = String(new LiveAPI("live_set tracks " + i).get("name")).toLowerCase();
        if (nm === want) return i;
    }
    return -1;
}

function buildMidi(song, t, res, plan) {
    var tpl = templateIndex(song, t.role), tr;
    if (tpl >= 0) {
        song.call("duplicate_track", tpl);                 // copy lands right after the template
        var idx = tpl + 1;
        var api = new LiveAPI("live_set tracks " + idx);
        api.set("name", t.name); api.set("color", t.color); api.set("mute", 0);
        tr = { api: api, index: idx };
        // remove clips the template may carry
        var old = ids(api, "arrangement_clips");
        for (var c = old.length - 1; c >= 0; c--) try { api.call("delete_clip", "id", old[c]); } catch (e) {}
        res.instrument = { loaded: ids(api, "devices").length > 0, from_template: "LB " + t.role };
    } else {
        tr = newTrack(song, "midi", t);
    }
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
    if (!res.instrument) res.instrument = loadInstrument(song, tr, t.instrument_candidates || []);
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
        var diag = {};
        try { diag.browser_id = br.id; diag.instruments_children = ids(new LiveAPI("live_app browser instruments"), "children").length; } catch (e) { diag.error = String(e); }
        return { loaded: false, note: "none of " + names.join(", ") + " found in the browser", browser: diag };
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
    var rp = readPlan(), plan = rp.plan;
    if (!step("read plan", !!plan, plan ? rp.path : rp)) return finish("live-verify.json");
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
    var failed = [], firstErr = "";
    for (var i = 0; i < R.steps.length; i++) if (!R.steps[i].ok) {
        failed.push(R.steps[i].step);
        if (!firstErr) { var d = R.steps[i].detail; firstErr = typeof d === "string" ? d : JSON.stringify(d); }
        firstErr = firstErr.replace(/[\u0080-\uffff]/g, "-");
    }
    R.summary = failed.length ? "FAILED: " + failed.join(" | ") : "ALL OK";
    var saved = writeJson(file, R);
    // status line carries the first error itself, so a screenshot is a full report
    show(R.phase + " - " + R.summary + (firstErr ? " :: " + firstErr.substring(0, 160) : "")
         + (saved ? " - report saved" : " - REPORT NOT SAVED (see Max console)"));
    if (firstErr.length > 160) post("LB first error (full): " + firstErr + "\n");
    post("LB report:\n" + JSON.stringify(R) + "\n");
}

function bang() { build(); }
