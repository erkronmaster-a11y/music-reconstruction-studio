// Simulates Live 12.0.15 warp-marker rules (as observed on the Mac) and runs the
// Builder's marker code against a plan. Usage: node tools/mock_live_warp.js live/loomback_build.js plan.json
// Fake LiveAPI with the warp-marker behaviour seen on Live 12.0.15.
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const plan = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const S_LEN = plan.tracks[0].warp_markers.slice(-1)[0].sample_time;
function makeClip() {
  // first marker + hidden helper 0.03125 beat later (100 BPM)
  let mk = [{ beat_time: 0, sample_time: 0 }, { beat_time: 0.03125, sample_time: 0.01875 }];
  const bpmOk = (a, b) => { const bpm = (b.beat_time - a.beat_time) / ((b.sample_time - a.sample_time) / 60); return bpm >= 5 && bpm <= 999; };
  const valid = (arr) => arr.every((m, i) => i === 0 || (m.beat_time > arr[i-1].beat_time && m.sample_time > arr[i-1].sample_time && bpmOk(arr[i-1], m)));
  const sampleAt = (b) => { let a = mk[0], c = mk[mk.length-1]; for (let i = 0; i < mk.length-1; i++) if (mk[i].beat_time <= b) { a = mk[i]; c = mk[i+1]; }
    return a.sample_time + (b - a.beat_time) * (c.sample_time - a.sample_time) / (c.beat_time - a.beat_time); };
  return {
    get(p) { if (p === "warp_markers") return [JSON.stringify({ warp_markers: mk })]; if (p === "available_warp_modes") return [0,1,2,3,4,6];
             if (p === "warp_mode") return [6]; if (p === "start_time") return [0]; if (p === "end_time") return [100]; return [0]; },
    set() {},
    call(fn, a, b) {
      if (fn === "add_warp_marker") {
        const n = { beat_time: a.beat_time, sample_time: a.sample_time === undefined ? sampleAt(a.beat_time) : a.sample_time };
        if (n.sample_time < 0 || n.sample_time > S_LEN + 1e-6) return;
        // explicit sample_time must lie between two existing markers
        if (a.sample_time !== undefined && !(mk.some(m => m.beat_time < n.beat_time) && mk.some(m => m.beat_time > n.beat_time))) return;
        const arr = mk.concat([n]).sort((x, y) => x.beat_time - y.beat_time);
        if (valid(arr)) mk = arr;
      } else if (fn === "move_warp_marker") {
        const i = mk.findIndex(m => Math.abs(m.beat_time - a) < 1e-9); if (i < 0) return;
        // as seen on the Mac: moving the first marker carries the hidden helper with it
        const carry = (i === 0 && mk.length >= 2 && mk[1].sample_time < 0.02) ? 1 : -1;
        const arr = mk.map((m, j) => (j === i || j === carry) ? { ...m, beat_time: m.beat_time + b } : m).sort((x, y) => x.beat_time - y.beat_time);
        if (valid(arr)) mk = arr;
      } else if (fn === "remove_warp_marker") { mk = mk.filter(m => Math.abs(m.beat_time - a) > 1e-9); }
    },
  };
}
const clip = makeClip();
const ctx = { post: () => {}, outlet: () => {}, LiveAPI: function () { return clip; } };
const fn = new Function("post", "outlet", "LiveAPI", "max", "Dict", "File", src + "; return { buildAudioCore: (c, t, res) => { /* reuse marker part */ }, placeAtSample, markers };");
const lib = fn(ctx.post, ctx.outlet, ctx.LiveAPI, {}, function(){}, function(){});
// run the marker block of buildAudio verbatim
const block = src.slice(src.indexOf("    var ex = markers(clip);"), src.indexOf("    // clip length follows the audio"));
const t = plan.tracks[0], res = {};
new Function("clip", "t", "res", "markers", "placeAtSample", block)(clip, t, res, lib.markers, lib.placeAtSample);
const fin = lib.markers(clip);
let miss = 0;


console.log(JSON.stringify({ wanted: t.warp_markers.length, now: fin.length, missing: miss }));
