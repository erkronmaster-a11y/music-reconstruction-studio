// MRS Bridge — Sprint 0 Live API test (Max for Live, classic [js] object).
//
// Two buttons in the device:
//   "run"    -> creates a MIDI track + arrangement clip with 4 known notes,
//               an audio track + arrangement clip from assets/test-tone.wav,
//               and records exactly which Live API calls worked.
//   "verify" -> after you save, close and reopen the Set: reads the notes
//               back and compares them with what "run" wrote.
//
// Results are written as JSON into <repo>/reports/sprint0/ (found from
// where this device file lives) and shown in the device itself.
//
// Rule: every step checks its own effect. LiveAPI does not throw on
// failure — it prints to the Max console and returns nothing — so a call
// counts as "ok" only when we can read back what it was supposed to do.

autowatch = 1;
inlets = 1;
outlets = 1;

var TRACK_NAME = "MRS Sprint0 MIDI";
var AUDIO_TRACK_NAME = "MRS Sprint0 Audio";
var CLIP_START = 4.0; // beats: bar 2, so "start time" is really tested
var CLIP_LEN = 4.0;
var TEST_TEMPO = 117.5; // deliberately not a round number
var TOL = 0.0005; // beats

// Four known notes. Note 3 is deliberately off-grid (microtiming check).
var EXPECTED = [
    { pitch: 60, start_time: 0.0, duration: 0.5, velocity: 100 },
    { pitch: 64, start_time: 1.0, duration: 0.5, velocity: 90 },
    { pitch: 67, start_time: 2.037, duration: 0.5, velocity: 80 },
    { pitch: 72, start_time: 3.0, duration: 0.75, velocity: 70 }
];

var result;

function newResult(phase) {
    return { phase: phase, time: new Date().toString(), live_version: null,
             max_version: max.version, steps: [], summary: "" };
}

function step(name, ok, detail) {
    result.steps.push({ step: name, ok: !!ok, detail: detail === undefined ? null : detail });
    post("MRS " + (ok ? "OK   " : "FAIL ") + name + (detail !== undefined ? " :: " + JSON.stringify(detail) : "") + "\n");
    return ok;
}

function show(msg) { outlet(0, "set", msg); }

function liveVersion() {
    try {
        var app = new LiveAPI("live_app");
        return app.call("get_major_version") + "." + app.call("get_minor_version") + "." + app.call("get_bugfix_version");
    } catch (e) { return "unknown: " + e; }
}

// ---------- paths ----------
function repoDir() {
    var p = this.patcher.filepath; // e.g. "Macintosh HD:/Users/x/.../live/MRS Bridge.amxd"
    if (!p) return null;
    var parts = String(p).split("/");
    parts.pop(); // file
    parts.pop(); // live/
    return parts.join("/");
}

// Sprint 0 lesson: File.isopen can be true while nothing reaches the disk.
// So every save is read back, and only a file we can read counts as saved.
function fileSize(path) {
    var f = new File(path, "read");
    if (!f.isopen) return 0;
    var n = f.eof;
    f.close();
    return n;
}

function writeVia(method, path, s) {
    try {
        if (method === "dict") {
            var d = new Dict();
            d.parse(s);
            d.export_json(path);
        } else {
            var f = new File(path, "write", "TEXT");
            if (!f.isopen) return 0;
            for (var i = 0; i < s.length; i += 2000) f.writestring(s.substring(i, i + 2000));
            f.eof = f.position;
            f.close();
        }
    } catch (e) { post("MRS: " + method + " write error " + e + "\n"); return 0; }
    return fileSize(path);
}

// Returns the path that was written and verified, or null.
function writeJson(name, obj) {
    var dir = repoDir();
    if (!dir) { post("MRS: device path unknown\n"); return null; }
    var s = JSON.stringify(obj, null, 2);
    var withVolume = dir + "/reports/sprint0/" + name;          // "Macintosh HD:/Users/…"
    var posix = withVolume.replace(/^[^\/]*:/, "");              // "/Users/…"
    var paths = [withVolume, posix];
    var methods = ["dict", "file"];
    for (var p = 0; p < paths.length; p++) {
        for (var m = 0; m < methods.length; m++) {
            var size = writeVia(methods[m], paths[p], s);
            post("MRS: save via " + methods[m] + " to " + paths[p] + " -> " + size + " bytes\n");
            if (size > 0) return paths[p];
        }
    }
    return null;
}

// ---------- helpers ----------
function idList(api, prop) {
    // get("arrangement_clips") returns ["id", 12, "id", 13 ...]
    var raw = api.get(prop), ids = [];
    if (!raw) return ids;
    for (var i = 0; i < raw.length; i++) if (raw[i] === "id" && raw[i + 1] !== 0) ids.push(raw[i + 1]);
    return ids;
}

function findTrack(song, name) {
    var n = song.getcount("tracks");
    for (var i = 0; i < n; i++) {
        var t = new LiveAPI("live_set tracks " + i);
        if (String(t.get("name")) === name) return { index: i, api: t };
    }
    return null;
}

function parseDict(ret) {
    if (ret === undefined || ret === null) return null;
    var s = (ret instanceof Array) ? ret.join(" ") : String(ret);
    try { return JSON.parse(s); } catch (e) { return { unparsed: s }; }
}

function readNotes(clip) {
    var d = parseDict(clip.call("get_notes_extended", 0, 128, 0.0, CLIP_LEN + 1));
    return (d && d.notes) ? d.notes : [];
}

function compareNotes(got) {
    var report = [], allOk = got.length === EXPECTED.length;
    var sorted = got.slice().sort(function (a, b) { return a.start_time - b.start_time; });
    for (var i = 0; i < EXPECTED.length; i++) {
        var e = EXPECTED[i], g = sorted[i];
        var ok = !!g && g.pitch === e.pitch && Math.abs(g.start_time - e.start_time) < TOL &&
                 Math.abs(g.duration - e.duration) < TOL && Math.abs(g.velocity - e.velocity) < 0.5;
        if (!ok) allOk = false;
        report.push({ expected: e, got: g || null, ok: ok });
    }
    return { ok: allOk, count: got.length, notes: report };
}

// ---------- "run" ----------
function run() {
    result = newResult("create");
    result.live_version = liveVersion();
    step("live_version", result.live_version.indexOf("12.") === 0, result.live_version);
    try { doRun(); } catch (e) { step("unexpected_exception", false, String(e)); }
    finish("live-create.json");
}

function doRun() {
    var song = new LiveAPI("live_set");
    step("open live_set", song.id !== 0, { id: song.id });

    // Tempo
    var oldTempo = song.get("tempo");
    song.set("tempo", TEST_TEMPO);
    var t = Number(song.get("tempo"));
    step("set tempo", Math.abs(t - TEST_TEMPO) < 0.001, { before: Number(oldTempo), after: t });

    // Clean up a previous run so verify reads one clean test
    var old = findTrack(song, TRACK_NAME);
    if (old) { song.call("delete_track", old.index); step("removed previous MIDI test track", !findTrack(song, TRACK_NAME)); }
    old = findTrack(song, AUDIO_TRACK_NAME);
    if (old) { song.call("delete_track", old.index); step("removed previous audio test track", !findTrack(song, AUDIO_TRACK_NAME)); }

    // MIDI track
    var before = song.getcount("tracks");
    song.call("create_midi_track", -1);
    var after = song.getcount("tracks");
    if (!step("create_midi_track", after === before + 1, { before: before, after: after })) return;
    var track = new LiveAPI("live_set tracks " + (after - 1));
    track.set("name", TRACK_NAME);
    step("set track name", String(track.get("name")) === TRACK_NAME, String(track.get("name")));
    track.set("color", 0x00e5ff);
    step("set track color", Number(track.get("color")) !== 0, Number(track.get("color")));

    // Arrangement MIDI clip
    track.call("create_midi_clip", CLIP_START, CLIP_LEN);
    var clipIds = idList(track, "arrangement_clips");
    if (!step("create_midi_clip (arrangement)", clipIds.length === 1, { clip_ids: clipIds })) return;
    var clip = new LiveAPI("id " + clipIds[0]);
    var st = Number(clip.get("start_time")), len = Number(clip.get("length"));
    step("clip position", Math.abs(st - CLIP_START) < TOL && Math.abs(len - CLIP_LEN) < TOL, { start_time: st, length: len });
    clip.set("name", "4-note test");

    // Notes: try the documented dict form; record which variant Live accepted.
    var method = null, got = [];
    var attempts = [
        ["add_new_notes(object)", function () { clip.call("add_new_notes", { notes: EXPECTED }); }],
        ["add_new_notes(json string)", function () { clip.call("add_new_notes", JSON.stringify({ notes: EXPECTED })); }],
        ["legacy set_notes", function () {
            clip.call("set_notes"); clip.call("notes", EXPECTED.length);
            for (var i = 0; i < EXPECTED.length; i++) {
                var n = EXPECTED[i]; clip.call("note", n.pitch, n.start_time.toFixed(6), n.duration.toFixed(6), n.velocity, 0);
            }
            clip.call("done");
        }]
    ];
    for (var a = 0; a < attempts.length && !method; a++) {
        try { attempts[a][1](); } catch (e) { step("notes via " + attempts[a][0], false, String(e)); continue; }
        got = readNotes(clip);
        if (got.length > 0) method = attempts[a][0];
        step("notes via " + attempts[a][0], got.length > 0, { notes_read_back: got.length });
    }
    result.note_method = method;
    var cmp = compareNotes(got);
    step("4 notes match exactly (incl. off-grid note)", cmp.ok, cmp);

    // Audio track + arrangement audio clip (needed in Sprint 3)
    var dir = repoDir();
    var wav = dir ? dir + "/assets/test-tone.wav" : null;
    var posix = wav ? wav.replace(/^[^\/]*:/, "") : null; // strip "Macintosh HD:" volume prefix
    before = song.getcount("tracks");
    song.call("create_audio_track", -1);
    after = song.getcount("tracks");
    if (!step("create_audio_track", after === before + 1, { before: before, after: after })) return;
    var at = new LiveAPI("live_set tracks " + (after - 1));
    at.set("name", AUDIO_TRACK_NAME);
    if (!posix) { step("create_audio_clip", false, "device path unknown"); return; }
    at.call("create_audio_clip", posix, CLIP_START);
    var aIds = idList(at, "arrangement_clips");
    var aInfo = null;
    if (aIds.length) {
        var ac = new LiveAPI("id " + aIds[0]);
        aInfo = { start_time: Number(ac.get("start_time")), file_path: String(ac.get("file_path")), warping: Number(ac.get("warping")) };
    }
    step("create_audio_clip (arrangement)", aIds.length === 1 && Math.abs(aInfo.start_time - CLIP_START) < TOL, { path: posix, clip: aInfo });
}

// ---------- "verify" (after save / close / reopen) ----------
function verify() {
    result = newResult("verify_after_reopen");
    result.live_version = liveVersion();
    try {
        var song = new LiveAPI("live_set");
        step("tempo survived", Math.abs(Number(song.get("tempo")) - TEST_TEMPO) < 0.001, Number(song.get("tempo")));
        var tr = findTrack(song, TRACK_NAME);
        if (step("MIDI test track present", !!tr, tr ? tr.index : null)) {
            var ids = idList(tr.api, "arrangement_clips");
            if (step("arrangement clip present", ids.length === 1, ids)) {
                var clip = new LiveAPI("id " + ids[0]);
                step("clip still at beat " + CLIP_START, Math.abs(Number(clip.get("start_time")) - CLIP_START) < TOL, Number(clip.get("start_time")));
                var cmp = compareNotes(readNotes(clip));
                step("4 notes match exactly after reopen", cmp.ok, cmp);
            }
        }
        var au = findTrack(song, AUDIO_TRACK_NAME);
        if (step("audio test track present", !!au)) {
            step("audio clip present", idList(au.api, "arrangement_clips").length === 1);
        }
    } catch (e) { step("unexpected_exception", false, String(e)); }
    finish("live-verify.json");
}

function finish(file) {
    var failed = [];
    for (var i = 0; i < result.steps.length; i++) {
        var s = result.steps[i];
        // A note variant that failed before a later variant worked is not a real failure.
        if (!s.ok && !(result.note_method && s.step.indexOf("notes via ") === 0)) failed.push(s.step);
    }
    // Failed step names go in the status line too, so a screenshot alone is a usable report.
    result.summary = failed.length === 0 ? "ALL OK" : "FAILED: " + failed.join(" | ");
    var saved = writeJson(file, result);
    show(result.phase + " — " + result.summary + (saved ? " — saved: " + saved : " — NOT SAVED"));
}

function bang() { run(); }
