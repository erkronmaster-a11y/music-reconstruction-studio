// Simulates Live 12.0.15's warp-marker behaviour as reported from the Mac
// (reports/sprint3/live-build.json, 2026-10-13) and runs the Builder's real
// buildAudio() against a plan:
//  - a new clip's first marker sits on the file's first sound (s0), not 0
//  - a hidden helper marker 0.03125 beat / 0.01875 s after it sets the tempo
//  - moving the first marker carries the helper along
//  - add_warp_marker is refused in every format (ADDS=1 env allows dict adds)
//  - the clip's start marker also sits on the first sound (Mac run 4);
//    UNWARPED=1 runs the warp-off path (buildUnwarped) instead
// Usage: node tools/mock_live_warp.js live/loomback_build.js plan.json [first_sound_s]
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const plan = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const S0 = parseFloat(process.argv[4] || "0.35");
const ALLOW_ADDS = process.env.ADDS === "1";
let mk = [{ beat_time: 0, sample_time: S0 }, { beat_time: 0.03125, sample_time: S0 + 0.01875 }];
const S_LEN = plan.tracks[0].warp_markers.slice(-1)[0].sample_time;
const UNWARPED = process.env.UNWARPED === "1";
const props = { warping: 1, start_marker: S0, loop_start: S0, end_marker: S_LEN, looping: 0, start_time: 0, end_time: 0 };
const bpmOk = (a, b) => { const bpm = (b.beat_time - a.beat_time) / ((b.sample_time - a.sample_time) / 60); return bpm >= 5 && bpm <= 999; };
const valid = (arr) => arr.every((m, i) => i === 0 || (m.beat_time > arr[i-1].beat_time && m.sample_time > arr[i-1].sample_time && bpmOk(arr[i-1], m)));
const clip = {
  id: 1,
  get(p) { if (p === "warp_markers") return [JSON.stringify({ warp_markers: mk })]; if (p === "available_warp_modes") return [0,1,2,3,4,6];
           if (p === "warp_mode") return [6]; if (p in props) return [props[p]]; return [0]; },
  set(p, v) { if (p === "start_marker" && v >= props.end_marker) return; props[p] = v; },
  call(fn, a, b) {
    if (fn === "add_warp_marker") {
      if (!ALLOW_ADDS || typeof a !== "object" || a.sample_time === undefined) return;
      if (!(mk.some(m => m.beat_time < a.beat_time) && mk.some(m => m.beat_time > a.beat_time))) return;
      const arr = mk.concat([{ beat_time: a.beat_time, sample_time: a.sample_time }]).sort((x, y) => x.beat_time - y.beat_time);
      if (valid(arr)) mk = arr;
    } else if (fn === "move_warp_marker") {
      const i = mk.findIndex(m => Math.abs(m.beat_time - a) < 1e-9); if (i < 0) return;
      const carry = (i === 0 && mk.length >= 2) ? 1 : -1;
      const arr = mk.map((m, j) => (j === i || j === carry) ? { ...m, beat_time: m.beat_time + b } : m).sort((x, y) => x.beat_time - y.beat_time);
      if (valid(arr)) mk = arr;
    } else if (fn === "remove_warp_marker") { mk = mk.filter(m => Math.abs(m.beat_time - a) > 1e-9); }
  },
};
let tracks = 0;
const song = { id: 9, getcount: () => tracks, get: () => [0], set() {}, call(fn) { if (/^create_/.test(fn)) tracks++; } };
const track = { id: 5, get: (p) => p === "arrangement_clips" ? ["id", 1] : [0], set() {},
                call(fn, path, pos) { if (fn === "create_audio_clip") props.start_time = pos; } };
function LiveAPI(path) { if (path === "live_set") return song; if (path === "id 1") return clip; return track; }
const lib = new Function("post", "outlet", "LiveAPI", "max", "Dict", "File",
  src + "; return { buildAudio, beatFromMarkers };")(() => {}, () => {}, LiveAPI, {}, function () {}, function () {});
// exercises the warp-marker path (constant plans normally use warp off; see buildUnwarped)
const t = Object.assign({}, plan.tracks.find(x => x.kind === "audio"), UNWARPED ? {} : { warp: true }), res = {};
try { lib.buildAudio(song, t, res); } catch (e) { res.error = String(e); }
const w = t.warp_markers, last = w[w.length - 1];
// how far, in beats, does the clip play from the plan at 20 points across the file?
let worst = 0;
for (let k = 0; k <= 20; k++) {
  const S = S0 + (last.sample_time - S0) * k / 20;
  let i = 0; while (i < w.length - 2 && w[i + 1].sample_time < S) i++;
  const planB = w[i].beat_time + (S - w[i].sample_time) * (w[i+1].beat_time - w[i].beat_time) / (w[i+1].sample_time - w[i].sample_time);
  worst = Math.max(worst, Math.abs(lib.beatFromMarkers(mk, S) - planB));
}
if (UNWARPED) { console.log(JSON.stringify({ method: res.warp_method, check: res.check, error: res.error || null, props })); process.exit(0); }
console.log(JSON.stringify({ markers: mk.length, method: res.warp_method, check: res.check, error: res.error || null,
                             worst_deviation_beats: Math.round(worst * 1000) / 1000 }));
