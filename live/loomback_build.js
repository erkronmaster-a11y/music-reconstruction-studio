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
    WARP_FORMAT = null; WARP_TRIED = [];
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
    if (t.warp === false) return buildUnwarped(tr, t, res);
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
    var last = want[want.length - 1];
    // Mac run 2: Live puts its first marker on the file's FIRST SOUND (0.04 s
    // into the mix, 0.35 s into the vocals), not at sample 0. Moving every
    // clip's first marker to the same beat shifted each stem differently.
    // The marker must go to the beat where ITS OWN sample belongs.
    if (!ex.length) throw "clip has no warp markers (warping off?)";
    var s0 = ex[0].sample_time, b0 = beatAt(want, s0);
    clip.call("move_warp_marker", ex[0].beat_time, b0 - ex[0].beat_time);   // Live carries its hidden helper along
    // Try the full per-beat warp (adds); every format was refused on 12.0.15.
    var added = 0;
    for (var m = 1; m < want.length; m++) {
        if (want[m].sample_time <= s0 + 0.03) continue;
        if (addMarker(clip, want[m].beat_time, want[m].sample_time)) added++;
        else if (WARP_FORMAT === null) break;   // no format works: stop trying
    }
    res.warp_add_format = WARP_FORMAT === null ? "none accepted" : WARP_FORMATS[WARP_FORMAT][0];
    res.warp_formats_tried = WARP_TRIED.slice(0, 8);
    if (added === 0) {
        // Two-marker fit with moves only: the helper marker right after the
        // first sets the clip's tempo. Point it so the clip runs at the song's
        // average tempo from this marker to the end → start and end line up.
        var now = markers(clip);
        if (now.length >= 2) {
            var h = now[1];
            var rate = (last.beat_time - b0) / Math.max(1e-6, last.sample_time - s0);   // beats per second
            var hb = b0 + rate * (h.sample_time - s0);
            clip.call("move_warp_marker", h.beat_time, hb - h.beat_time);
        }
        res.warp_method = "two-marker fit (adds not accepted by this Live): aligned start, average tempo";
        res.average_tempo_bpm = Math.round(rate * 60 * 1000) / 1000;
    } else {
        res.warp_method = "per-beat markers via " + res.warp_add_format;
    }
    // clip length follows the audio
    try { clip.set("end_marker", last.beat_time); clip.set("loop_end", last.beat_time); } catch (e) {}
    var fin = markers(clip);
    res.markers_now = fin.length;
    res.first_marker = fin[0];
    res.clip_start = Number(clip.get("start_time"));
    res.clip_end = Number(clip.get("end_time"));
    // check where the clip's end and start now play, against the plan
    var endBeat = beatFromMarkers(fin, last.sample_time), startBeat = beatFromMarkers(fin, s0);
    res.check = { start_error_beats: Math.round((startBeat - b0) * 1000) / 1000,
                  end_error_beats: Math.round((endBeat - last.beat_time) * 1000) / 1000 };
    if (Math.abs(res.check.start_error_beats) > 0.01 || Math.abs(res.check.end_error_beats) > 0.05)
        res.error = "clip not where the plan puts it: " + JSON.stringify(res.check);
}

// plan markers (sample→beat), piecewise linear; extrapolated at the ends
function beatAt(want, S) {
    if (S <= want[0].sample_time) {
        var r0 = (want[1].beat_time - want[0].beat_time) / (want[1].sample_time - want[0].sample_time);
        return want[0].beat_time + (S - want[0].sample_time) * r0;
    }
    for (var i = 0; i < want.length - 1; i++)
        if (S <= want[i + 1].sample_time)
            return want[i].beat_time + (S - want[i].sample_time) * (want[i + 1].beat_time - want[i].beat_time) / (want[i + 1].sample_time - want[i].sample_time);
    var n = want.length;
    return want[n - 1].beat_time + (S - want[n - 1].sample_time) * (want[n - 1].beat_time - want[n - 2].beat_time) / (want[n - 1].sample_time - want[n - 2].sample_time);
}
// where Live will play sample S, from the clip's own markers (last segment extrapolated)
function beatFromMarkers(mk, S) {
    if (mk.length < 2) return NaN;
    var a = mk[0], b = mk[1];
    for (var i = 0; i < mk.length - 1; i++) if (mk[i].sample_time <= S) { a = mk[i]; b = mk[i + 1]; }
    return a.beat_time + (S - a.sample_time) * (b.beat_time - a.beat_time) / (b.sample_time - a.sample_time);
}

// add_warp_marker: on Live 12.0.15 every add was refused while moves worked,
// so the argument format is in doubt. Try each plausible form once, keep the
// first one that adds a marker, and report it (like add_new_notes in Sprint 0).
var WARP_FORMAT = null;
var WARP_FORMATS = [
    ["dict object", function (c, b, s) { c.call("add_warp_marker", s === undefined ? { beat_time: b } : { beat_time: b, sample_time: s }); }],
    ["json string", function (c, b, s) { c.call("add_warp_marker", JSON.stringify(s === undefined ? { beat_time: b } : { beat_time: b, sample_time: s })); }],
    ["key value list", function (c, b, s) { if (s === undefined) c.call("add_warp_marker", "beat_time", b); else c.call("add_warp_marker", "beat_time", b, "sample_time", s); }],
    ["positional", function (c, b, s) { if (s === undefined) c.call("add_warp_marker", b); else c.call("add_warp_marker", b, s); }]
];
var WARP_TRIED = [];
function addMarker(clip, b, s) {
    var n0 = markers(clip).length;
    if (WARP_FORMAT !== null) { WARP_FORMATS[WARP_FORMAT][1](clip, b, s); return markers(clip).length > n0; }
    for (var f = 0; f < WARP_FORMATS.length; f++) {
        try { WARP_FORMATS[f][1](clip, b, s); } catch (e) {}
        var ok = markers(clip).length > n0;
        WARP_TRIED.push({ format: WARP_FORMATS[f][0], with_sample: s !== undefined, ok: ok });
        if (ok) { WARP_FORMAT = f; return true; }
    }
    return false;
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
    var added = addMarker(clip, b0);
    if (added) clip.call("move_warp_marker", b0, B - b0);
    var after = markers(clip), best = null;
    for (var k = 0; k < after.length; k++) if (!best || Math.abs(after[k].beat_time - B) < Math.abs(best.beat_time - B)) best = after[k];
    return { asked: { beat_time: B, sample_time: S }, got: best, added: added };
}

// Warp OFF: the file plays at its real speed from an exact beat position.
// Audio and MIDI share one tempo, so they stay together for the whole song.
function buildUnwarped(tr, t, res) {
    tr.api.call("create_audio_clip", posix(t.file), t.position_beats);
    var cids = ids(tr.api, "arrangement_clips");
    if (cids.length !== 1) throw "create_audio_clip made no clip for " + t.file;
    var clip = new LiveAPI("id " + cids[0]);
    clip.set("warping", 0);
    res.warp_method = "warp off, placed at beat " + t.position_beats;
    res.warping = Number(clip.get("warping"));
    res.clip_start = Number(clip.get("start_time"));
    res.check = { start_error_beats: Math.round((res.clip_start - t.position_beats) * 10000) / 10000 };
    if (Math.abs(res.check.start_error_beats) > 0.001) res.error = "clip start " + res.clip_start + " instead of " + t.position_beats;
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
    if (!res.instrument) res.instrument = insertNative(tr, t.role);
    if (!res.instrument || !res.instrument.loaded) {
        var b = loadInstrument(song, tr, t.instrument_candidates || []);
        res.instrument = { insert_device: res.instrument, browser: b, loaded: !!(b && b.loaded) };
    }
}

// Track.insert_device (documented, Live 12.3+): native instruments by name.
// Bass/melody get Drift; drums get Drum Rack (empty until a kit is dropped in —
// a native device cannot carry samples).
var NATIVE = { bass: "Drift", melody: "Drift", drums: "Drum Rack" };
function insertNative(tr, role) {
    var name = NATIVE[role];
    if (!name) return null;
    var before = ids(tr.api, "devices").length;
    try { tr.api.call("insert_device", name); } catch (e) { return { loaded: false, tried: "insert_device " + name, error: String(e) }; }
    var after = ids(tr.api, "devices").length;
    return { loaded: after > before, device: name, via: "insert_device",
             note: after > before ? null : "not available (needs Live 12.3 or later)" };
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
            if (t.warp === false) {
                var st = Number(clip.get("start_time"));
                step("placed: " + t.name, Math.abs(st - t.position_beats) < 0.001,
                     { start: st, wanted: t.position_beats, warping: Number(clip.get("warping")) });
                continue;
            }
            var mk = markers(clip), w = t.warp_markers, lastW = w[w.length - 1];
            var endErr = beatFromMarkers(mk, lastW.sample_time) - lastW.beat_time;
            var startErr = beatFromMarkers(mk, mk[0].sample_time) - beatAt(w, mk[0].sample_time);
            step("warp: " + t.name, Number(clip.get("warping")) === 1 && Math.abs(startErr) < 0.01 && Math.abs(endErr) < 0.05,
                 { markers: mk.length, per_beat: mk.length >= w.length, start_error_beats: Math.round(startErr * 1000) / 1000,
                   end_error_beats: Math.round(endErr * 1000) / 1000 });
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
    if (R.phase === "build" && R.tracks) {
        var made = 0, midiOk = 0, midi = 0, warpOk = 0, audio = 0, inst = 0;
        for (var k = 0; k < R.tracks.length; k++) {
            var tk = R.tracks[k];
            if (!tk.error || tk.kind === "audio") made++;
            if (tk.kind === "midi") { midi++; if (!tk.error) midiOk++; if (tk.instrument && tk.instrument.loaded) inst++; }
            else { audio++; if (!tk.error) warpOk++; }
        }
        R.summary = made + " tracks built | MIDI " + midiOk + "/" + midi + " exact | warped " + warpOk + "/" + audio +
                    " | instruments " + inst + "/" + midi + (failed.length ? " (details in report)" : "");
    }
    var saved = writeJson(file, R);
    // status line carries the first error itself, so a screenshot is a full report
    show(R.phase + " - " + R.summary + (firstErr ? " :: " + firstErr.substring(0, 160) : "")
         + (saved ? " - report saved" : " - REPORT NOT SAVED (see Max console)"));
    if (firstErr.length > 160) post("LB first error (full): " + firstErr + "\n");
    post("LB report:\n" + JSON.stringify(R) + "\n");
}

function bang() { build(); }
