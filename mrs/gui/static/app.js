// Loomback — front end. Plain JS, no build step. Talks to mrs/gui/server.py.
"use strict";
const $ = (s) => document.querySelector(s);
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  const j = r.headers.get("content-type")?.includes("json") ? await r.json() : null;
  if (!r.ok) throw new Error(j?.error || r.statusText);
  return j;
};
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const fmt = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`;
const log = (line) => { const el = $("#log"); el.textContent += line + "\n"; el.scrollTop = el.scrollHeight; };

const COLORS = { mix: "#edf0f4", bass: "#2aa8ff", melody: "#ff3fbd", drums: "#48ff91", click: "#efff36", stem: "#8fd3c9" };
const DRUM_ROWS = { 46: "OPEN HAT", 42: "HAT", 39: "OTHER", 38: "SNARE", 36: "KICK" };
const S = {
  dir: null, data: null, duration: 0,
  ctx: null, buffers: {}, channels: [], playing: false, t0: 0, offset: 0, sched: new Set(), timer: null,
  pxPerSec: 60, scroll: 0, peaks: null,
};

// ---------- left panel ----------
document.querySelectorAll(".tab").forEach((b) => b.onclick = () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".tab-body").forEach((x) => x.hidden = x.id !== "tab-" + b.dataset.tab);
  if (b.dataset.tab === "traktor" && !S.traktor) loadTraktor();
});

async function loadProjects() {
  const list = await api("/api/projects");
  const ul = $("#projectList");
  ul.innerHTML = list.length ? "" : `<li class="empty">No projects yet — use Traktor or Add song.</li>`;
  for (const p of list) {
    const li = document.createElement("li");
    li.classList.toggle("active", p.dir === S.dir);
    li.innerHTML = `<b></b><small>${p.tempo ? p.tempo.toFixed(2) + " BPM · " : ""}${p.mode || ""}${p.tracks.length ? " · MIDI ✓" : ""} · ${p.modified}</small>`;
    li.querySelector("b").textContent = p.name;
    li.onclick = () => openProject(p.dir);
    ul.append(li);
  }
}

async function loadTraktor(refresh) {
  $("#traktorList").innerHTML = `<li class="empty">Reading Traktor stems… (first time ≈ 1 min)</li>`;
  S.traktor = await api("/api/traktor" + (refresh ? "?refresh=1" : ""));
  renderTraktor();
}
function renderTraktor() {
  const q = $("#traktorFilter").value.toLowerCase();
  const ul = $("#traktorList");
  ul.innerHTML = "";
  const items = S.traktor.items.filter((i) => !q || i.title.toLowerCase().includes(q));
  if (!items.length) ul.innerHTML = `<li class="empty">Nothing in ${S.traktor.folder}</li>`;
  for (const i of items) {
    const li = document.createElement("li");
    li.className = i.titled ? "" : "untitled";
    li.innerHTML = `<b></b><small>${i.date}${i.titled ? "" : " · title unknown"}</small>`;
    li.querySelector("b").textContent = i.title;
    li.title = i.path;
    li.onclick = () => analyze(i.path);
    ul.append(li);
  }
}
$("#traktorFilter").oninput = renderTraktor;
$("#traktorRefresh").onclick = () => loadTraktor(true);

const dz = $("#dropZone");
dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("over"); };
dz.ondragleave = () => dz.classList.remove("over");
dz.ondrop = async (e) => {
  e.preventDefault(); dz.classList.remove("over");
  const f = e.dataTransfer.files[0];
  if (!f) return;
  log(`Uploading ${f.name} (${(f.size / 1e6).toFixed(1)} MB)…`);
  const r = await api("/api/upload", { method: "POST", headers: { "X-Filename": f.name }, body: f });
  analyze(r.path);
};
$("#pathGo").onclick = () => $("#pathInput").value.trim() && analyze($("#pathInput").value.trim());

// ---------- jobs ----------
async function runJob(body, label) {
  log(`\n▶ ${label}`);
  let job;
  try { ({ job } = await post("/api/run", body)); }
  catch (e) { log("✖ could not start: " + e.message); return { state: "failed" }; }
  return watchJob(job, label);
}
async function watchJob(job, label) {
  const pill = $("#jobPill");
  pill.hidden = false; pill.className = "job-pill"; $("#jobText").textContent = label + "…";
  setBusy(true);
  let seen = 0;
  while (true) {
    await new Promise((r) => setTimeout(r, 700));
    let j;
    try { j = await api("/api/job?id=" + job); }
    catch (e) { log("✖ lost contact with Loomback — is the Terminal window still open?"); setBusy(false); return { state: "failed" }; }
    j.log.slice(seen).forEach(log); seen = j.log.length;
    if (j.state !== "running") {
      pill.className = "job-pill " + (j.state === "done" ? "ok" : "fail");
      $("#jobText").textContent = `${label} ${j.state === "done" ? "done" : "FAILED"} (${j.seconds}s)`;
      setBusy(false);
      return j;
    }
  }
}
function setBusy(b) {
  ["#btnTranscribe", "#btnLive", "#btnRedetect", "#btnTempo", "#btnClear", "#pathGo"].forEach((s) => $(s).disabled = b || (s !== "#pathGo" && !S.dir));
}
async function analyze(src) {
  const j = await runJob({ action: "analyze", src }, "Analysing");
  if (j.state === "done" && j.result) { await loadProjects(); openProject(j.result); }
}
$("#btnTranscribe").onclick = async () => { await runJob({ action: "all", dir: S.dir }, "Transcribing + exporting"); openProject(S.dir); };
$("#btnLive").onclick = async () => {
  if (!S.data.project.tracks.length) { log("Run step 1 first — there is no MIDI to send yet."); return; }
  await runJob({ action: "live", dir: S.dir }, "Preparing the Ableton build");
};
$("#btnRedetect").onclick = async () => { await runJob({ action: "redetect", dir: S.dir }, "Re-detecting timing"); openProject(S.dir); };
$("#btnTempo").onclick = async () => {
  await runJob({ action: "tempo", dir: S.dir, bpm: $("#bpmIn").value, downbeat: $("#downIn").value }, "Saving timing correction");
  openProject(S.dir);
};
$("#btnClear").onclick = async () => { await runJob({ action: "clear", dir: S.dir }, "Clearing correction"); openProject(S.dir); };
$("#btnFinder").onclick = () => post("/api/open", { path: S.dir });
$("#logClear").onclick = () => $("#log").textContent = "";

// ---------- rename / auto-name ----------
function startRename(value) {
  const inp = $("#nameIn");
  $("#projName").hidden = true; inp.hidden = false;
  inp.value = value ?? S.data.project.name; inp.focus(); inp.select();
}
async function doRename(name) {
  $("#nameIn").hidden = true; $("#projName").hidden = false; $("#nameList").hidden = true;
  name = name.trim();
  if (!name || name === S.data.project.name) return;
  const j = await runJob({ action: "rename", dir: S.dir, name }, "Renaming");
  if (j.state === "done" && j.result) openProject(j.result);
}
$("#projName").onclick = () => S.dir && startRename();
$("#btnRename").onclick = () => startRename();
$("#nameIn").onkeydown = (e) => {
  if (e.key === "Enter") doRename(e.target.value);
  if (e.key === "Escape") { e.target.hidden = true; $("#projName").hidden = false; }
};
$("#nameIn").onblur = (e) => setTimeout(() => { if (!e.target.hidden) doRename(e.target.value); }, 150);
$("#btnAutoname").onclick = async () => {
  const ul = $("#nameList");
  if (!ul.hidden) { ul.hidden = true; return; }
  ul.hidden = false; ul.innerHTML = `<li class="empty">Reading the song's files…</li>`;
  const names = await api("/api/names?dir=" + encodeURIComponent(S.dir));
  ul.innerHTML = names.length ? "" : `<li class="empty">No name found in tags, Traktor or file names — use ✎ to type one.</li>`;
  for (const c of names) {
    const li = document.createElement("li");
    li.innerHTML = `<b></b><small></small>`;
    li.querySelector("b").textContent = c.name; li.querySelector("small").textContent = "from " + c.source;
    li.onclick = () => { ul.hidden = true; startRename(c.name); };   // confirm with Enter
    ul.append(li);
  }
};

// ---------- project ----------
async function openProject(dir) {
  stop();
  const data = await api("/api/project?dir=" + encodeURIComponent(dir));
  S.dir = dir; S.data = data; S.buffers = {}; S.peaks = null;
  const m = data.project;
  const mix = m.sources.find((s) => s.role === "mix");
  S.duration = mix.duration_s;
  $("#projName").textContent = m.name;
  $("#projMeta").textContent = `${fmt(S.duration)} · ${m.sources.length - 1} stems · ${m.tracks.length ? m.tracks.map((t) => t.id).join(" + ") + " MIDI" : "no MIDI yet"}`;
  $("#emptyStage").hidden = true;
  ["#btnPlay", "#btnStop", "#btnFinder", "#btnRename", "#btnAutoname"].forEach((s) => $(s).disabled = false);
  setBusy(false);
  renderTiming(); renderParts(); buildMixer();
  loadProjects();
  S.scroll = 0; draw();
  ensureBuffer("mix");
}

function timingView() {
  const d = S.data.project.timing.detected || {};
  const c = S.data.project.timing.correction;
  const bm = d.beat_map || {};
  if (!c && d.export_mode === "beatmap" && bm.beats_s) return { beats: bm.beats_s, downs: new Set(bm.downbeats_s), kind: "beat map" };
  const bpm = c?.tempo_bpm ?? d.tempo_bpm, first = c?.first_downbeat_s ?? d.first_downbeat_s ?? 0, bpb = c?.beats_per_bar ?? 4;
  const p = 60 / bpm, beats = [], downs = new Set();
  for (let k = -Math.floor(first / p); first + k * p <= S.duration; k++) {
    const t = +(first + k * p).toFixed(5); beats.push(t);
    if (((k % bpb) + bpb) % bpb === 0) downs.add(t);
  }
  return { beats, downs, kind: c ? "your correction" : "one tempo" };
}

function renderTiming() {
  const d = S.data.project.timing.detected || {}, c = S.data.project.timing.correction, bm = d.beat_map || {};
  const g = d.constant_grid_gap_ms || {};
  $("#modeOut").textContent = c ? "manual" : (d.export_mode || "");
  const rows = [
    ["Tempo", (c?.tempo_bpm ?? d.tempo_bpm)?.toFixed(3) + " BPM" + (c?.tempo_bpm ? " ·you" : "")],
    ["1st downbeat", (c?.first_downbeat_s ?? d.first_downbeat_s)?.toFixed(3) + " s" + (c?.first_downbeat_s != null ? " ·you" : "")],
    ["Export mode", c ? "constant (your correction)" : d.export_mode === "beatmap" ? "beat map (Live warps audio)" : "one tempo, no warping"],
    ["Grid vs beats", g.p95 != null ? `${g.median} ms · 95% ${g.p95} ms` : "–", g.p95 > 20],
    ["Beat map", bm.beats_s ? `${bm.beats_s.length} beats · ${bm.downbeats_s.length} bars` : "–"],
    ["Odd bars", bm.irregular_bars ? String(bm.irregular_bars.length) : "–", bm.irregular_bars?.length > 0],
  ];
  $("#timingKv").innerHTML = rows.map(([k, v, w]) => `<dt>${k}</dt><dd class="${w ? "warn" : ""}">${v}</dd>`).join("");
  $("#bpmIn").value = ""; $("#downIn").value = "";
  $("#bpmIn").placeholder = (c?.tempo_bpm ?? d.tempo_bpm)?.toFixed(3) || "BPM";
  $("#downIn").placeholder = (c?.first_downbeat_s ?? d.first_downbeat_s)?.toFixed(3) || "1st downbeat s";
}

function renderParts() {
  const rows = [];
  for (const t of S.data.project.tracks) {
    const n = t.notes_view, flagged = n.filter((x) => x.flags?.length).length;
    const low = n.filter((x) => x.confidence < 0.3).length;
    const rv = S.data.review?.[t.id];
    rows.push([t.id, `${n.length - flagged} notes${flagged ? ` (+${flagged} flagged)` : ""}`]);
    rows.push(["  low confidence", String(low), low > n.length * 0.3]);
    if (rv?.chroma_agreement_0to1 != null) rows.push(["  sounds like source*", rv.chroma_agreement_0to1.toFixed(2)]);
    rows.push(["  method", t.raw.method.split(" (")[0]]);
  }
  $("#partsKv").innerHTML = rows.length
    ? rows.map(([k, v, w]) => `<dt>${k}</dt><dd class="${w ? "warn" : ""}">${v}</dd>`).join("") + `<dt style="grid-column:1/-1;color:var(--muted-2)">* rough chroma match — a listening aid, not accuracy</dt>`
    : `<dt>No MIDI yet</dt><dd>run step 1</dd>`;
}

// ---------- mixer / audio ----------
function buildMixer() {
  const m = S.data.project;
  S.channels = [{ id: "mix", label: "Full mix", kind: "audio", src: m.sources.find((s) => s.role === "mix"), on: true, vol: 0.8, color: COLORS.mix }];
  for (const s of m.sources.filter((s) => s.role !== "mix"))
    S.channels.push({ id: s.id, label: `Stem · ${s.id}`, kind: "audio", src: s, on: false, vol: 0.8, color: COLORS.stem });
  for (const t of m.tracks)
    S.channels.push({ id: "midi-" + t.id, label: `MIDI · ${t.id}`, kind: "midi", track: t, on: false, vol: 0.5, color: COLORS[t.id] || COLORS.melody });
  S.channels.push({ id: "click", label: "Click (beats)", kind: "click", on: false, vol: 0.5, color: COLORS.click });
  const box = $("#mixer"); box.innerHTML = "";
  for (const ch of S.channels) {
    const row = document.createElement("div"); row.className = "ch";
    row.innerHTML = `<button title="on/off">${ch.kind === "audio" ? "A" : ch.kind === "midi" ? "M" : "C"}</button><span></span><input type="range" min="0" max="1" step="0.01" value="${ch.vol}">`;
    const btn = row.querySelector("button"), lab = row.querySelector("span");
    lab.textContent = ch.label;
    const paint = () => { btn.classList.toggle("on", ch.on); btn.style.background = ch.on ? ch.color : ""; };
    btn.onclick = async () => {
      ch.on = !ch.on; paint();
      if (ch.on && ch.kind === "audio") { lab.textContent = ch.label + " (loading…)"; await ensureBuffer(ch.id); lab.textContent = ch.label; }
      if (S.playing) { const t = now(); stop(true); play(t); }
    };
    row.querySelector("input").oninput = (e) => { ch.vol = +e.target.value; if (ch.gain) ch.gain.gain.value = ch.vol; };
    paint(); box.append(row);
  }
}

function audioCtx() { return S.ctx || (S.ctx = new AudioContext()); }
async function ensureBuffer(id) {
  if (S.buffers[id]) return S.buffers[id];
  const ch = S.channels.find((c) => c.id === id);
  const r = await fetch("/api/audio?path=" + encodeURIComponent(ch.src.path));
  const buf = await audioCtx().decodeAudioData(await r.arrayBuffer());
  S.buffers[id] = buf;
  if (id === "mix") { S.peaks = peaks(buf); draw(); }
  return buf;
}
function peaks(buf, hop = 256) {
  const a = buf.getChannelData(0), b = buf.numberOfChannels > 1 ? buf.getChannelData(1) : a;
  const n = Math.floor(a.length / hop), out = new Float32Array(n);
  for (let i = 0; i < n; i++) { let m = 0; for (let j = i * hop; j < (i + 1) * hop; j += 4) m = Math.max(m, Math.abs(a[j] + b[j]) / 2); out[i] = m; }
  return { data: out, perSec: buf.sampleRate / hop };
}

const now = () => S.playing ? S.offset + (audioCtx().currentTime - S.t0) : S.offset;
async function play(from) {
  const ctx = audioCtx(); await ctx.resume();
  // load every stem first: a buffer that arrives after the start time would
  // start late, out of step with the MIDI scheduled against the same clock
  await Promise.all(S.channels.filter((c) => c.on && c.kind === "audio").map((c) => ensureBuffer(c.id)));
  S.offset = Math.max(0, Math.min(from ?? S.offset, S.duration)); S.t0 = ctx.currentTime + 0.05; S.playing = true; S.sched = new Set();
  for (const ch of S.channels) {
    if (!ch.on) continue;
    ch.gain = ctx.createGain(); ch.gain.gain.value = ch.vol; ch.gain.connect(ctx.destination);
    if (ch.kind === "audio") {
      const buf = await ensureBuffer(ch.id);
      const src = ctx.createBufferSource(); src.buffer = buf; src.connect(ch.gain);
      // stems with a sync offset play shifted so they line up with the mix
      const off = ch.src.sync?.offset_s || 0;
      src.start(S.t0, Math.max(0, S.offset + off)); ch.node = src;
    }
  }
  $("#btnPlay").textContent = "❚❚ Pause";
  S.timer = setInterval(schedule, 30); schedule(); tick();
}
function schedule() {
  const ctx = audioCtx(), t = now(), until = t + 0.2;
  for (const ch of S.channels) {
    if (!ch.on || !ch.gain) continue;
    if (ch.kind === "midi") {
      ch.track.notes_view.forEach((n, i) => {
        const key = ch.id + i;
        if ((n.flags?.length && ch.track.id !== "drums") || S.sched.has(key) || n.start_s < t - 0.01 || n.start_s >= until) return;
        S.sched.add(key);
        const at = S.t0 + (n.start_s - S.offset), dur = Math.max(0.03, n.end_s - n.start_s);
        if (ch.track.id === "drums") { drumHit(ctx, ch.gain, at, n); return; }
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.type = ch.track.id === "bass" ? "triangle" : "square";
        o.frequency.value = 440 * 2 ** ((n.pitch - 69) / 12);
        const v = (n.velocity / 127) * (ch.track.id === "bass" ? 0.9 : 0.25);
        g.gain.setValueAtTime(0, at); g.gain.linearRampToValueAtTime(v, at + 0.005);
        g.gain.setValueAtTime(v, at + dur - 0.01); g.gain.linearRampToValueAtTime(0, at + dur);
        o.connect(g).connect(ch.gain); o.start(at); o.stop(at + dur + 0.02);
      });
    } else if (ch.kind === "click") {
      const tv = timingView();
      tv.beats.forEach((b) => {
        const key = "c" + b;
        if (S.sched.has(key) || b < t - 0.01 || b >= until) return;
        S.sched.add(key);
        const at = S.t0 + (b - S.offset), o = ctx.createOscillator(), g = ctx.createGain();
        o.frequency.value = tv.downs.has(b) ? 1760 : 880;
        g.gain.setValueAtTime(0.6, at); g.gain.exponentialRampToValueAtTime(0.001, at + 0.04);
        o.connect(g).connect(ch.gain); o.start(at); o.stop(at + 0.05);
      });
    }
  }
}
let NOISE = null;
function drumHit(ctx, out, at, n) {
  const v = n.velocity / 127, g = ctx.createGain();
  if (n.pitch === 36) {               // kick: falling sine
    const o = ctx.createOscillator(); o.frequency.setValueAtTime(120, at); o.frequency.exponentialRampToValueAtTime(45, at + 0.12);
    g.gain.setValueAtTime(v, at); g.gain.exponentialRampToValueAtTime(0.001, at + 0.25);
    o.connect(g).connect(out); o.start(at); o.stop(at + 0.26); return;
  }
  if (!NOISE) { NOISE = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate); const d = NOISE.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1; }
  const src = ctx.createBufferSource(), f = ctx.createBiquadFilter();
  src.buffer = NOISE;
  f.type = n.pitch === 38 ? "bandpass" : n.pitch === 39 ? "bandpass" : "highpass";
  f.frequency.value = n.pitch === 38 ? 2500 : n.pitch === 39 ? 900 : 7000;
  const len = n.pitch === 46 ? 0.35 : n.pitch === 38 ? 0.15 : 0.05;
  g.gain.setValueAtTime(v * 0.6, at); g.gain.exponentialRampToValueAtTime(0.001, at + len);
  src.connect(f).connect(g).connect(out); src.start(at); src.stop(at + len + 0.01);
}
function stop(keep) {
  if (S.playing) S.offset = now();
  if (!keep && !S.playing) S.offset = 0;
  S.playing = false; clearInterval(S.timer);
  for (const ch of S.channels) { try { ch.node?.stop(); } catch {} ch.gain?.disconnect(); ch.node = ch.gain = null; }
  $("#btnPlay").textContent = "▶ Play"; draw();
}
$("#btnPlay").onclick = () => S.playing ? stop(true) : play();
$("#btnStop").onclick = () => { stop(); S.offset = 0; S.scroll = 0; draw(); };
document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && S.dir && e.target.tagName !== "INPUT") { e.preventDefault(); $("#btnPlay").click(); }
});
function tick() { if (!S.playing) return; const t = now(); if (t >= S.duration) { stop(); return; } follow(t); draw(); requestAnimationFrame(tick); }

// ---------- timeline ----------
const cv = $("#timeline");
const viewSec = () => cv.clientWidth / S.pxPerSec;
function follow(t) { if (t > S.scroll + viewSec() * 0.85 || t < S.scroll) { S.scroll = Math.max(0, t - viewSec() * 0.15); syncScroll(); } }
function syncScroll() { $("#scroll").value = S.duration ? (S.scroll / Math.max(1, S.duration - viewSec())) * 1000 : 0; }
$("#scroll").oninput = (e) => { S.scroll = (e.target.value / 1000) * Math.max(0, S.duration - viewSec()); draw(); };
$("#zoom").oninput = (e) => { S.pxPerSec = +e.target.value; draw(); };
cv.addEventListener("wheel", (e) => {
  e.preventDefault();
  if (e.ctrlKey || e.metaKey) { S.pxPerSec = Math.min(400, Math.max(10, S.pxPerSec * (e.deltaY < 0 ? 1.15 : 0.87))); $("#zoom").value = S.pxPerSec; }
  else S.scroll = Math.max(0, Math.min(S.duration - viewSec(), S.scroll + (e.deltaX || e.deltaY) / S.pxPerSec));
  syncScroll(); draw();
}, { passive: false });
cv.onclick = (e) => {
  if (!S.dir) return;
  const t = S.scroll + e.offsetX / S.pxPerSec;
  if (S.playing) { stop(true); play(t); } else { S.offset = t; draw(); }
};
window.onresize = draw;

function draw() {
  const dpr = devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W * dpr; cv.height = H * dpr;
  const g = cv.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
  if (!S.data) return;
  const x = (t) => (t - S.scroll) * S.pxPerSec, t1 = S.scroll + W / S.pxPerSec;
  const tracks = S.data.project.tracks;
  const waveH = tracks.length ? H * 0.3 : H, laneH = tracks.length ? (H - waveH) / tracks.length : 0;
  // beats
  const tv = timingView();
  let bar = 0;
  tv.beats.forEach((b) => {
    const isDown = tv.downs.has(b); if (isDown) bar++;
    if (b < S.scroll || b > t1) return;
    g.fillStyle = isDown ? "rgba(239,255,54,.55)" : "rgba(52,61,71,.7)";
    g.fillRect(Math.round(x(b)), 0, 1, H);
    if (isDown && S.pxPerSec * (tv.beats[1] - tv.beats[0]) * 4 > 34) { g.fillStyle = "#8a9200"; g.font = "9px ui-monospace"; g.fillText(String(bar), x(b) + 3, 10); }
  });
  // waveform
  if (S.peaks) {
    const p = S.peaks, mid = waveH / 2;
    g.fillStyle = "rgba(237,240,244,.55)";
    for (let px = 0; px < W; px++) {
      const i = Math.floor((S.scroll + px / S.pxPerSec) * p.perSec), j = Math.floor((S.scroll + (px + 1) / S.pxPerSec) * p.perSec);
      let m = 0; for (let k = i; k <= j && k < p.data.length; k++) m = Math.max(m, p.data[k]);
      const h = m * waveH * 0.9; g.fillRect(px, mid - h / 2, 1, Math.max(1, h));
    }
  } else { g.fillStyle = "#525b66"; g.font = "11px ui-monospace"; g.fillText("loading audio…", 10, waveH / 2); }
  // lanes
  tracks.forEach((t, li) => {
    const y0 = waveH + li * laneH, col = COLORS[t.id] || COLORS.melody;
    g.fillStyle = "rgba(13,16,20,.85)"; g.fillRect(0, y0, W, 1);
    const isDrum = t.id === "drums", order = [46, 42, 39, 38, 36];
    const ps = t.notes_view.map((n) => n.pitch), lo = isDrum ? 0 : Math.min(...ps) - 1, hi = isDrum ? order.length : Math.max(...ps) + 1, rowH = (laneH - 14) / Math.max(1, hi - lo);
    const rowOf = (p) => isDrum ? order.indexOf(p) + 0.5 : hi - p;
    if (isDrum && rowH > 9) { g.fillStyle = "#3d6b52"; g.font = "8px ui-monospace"; order.forEach((p, k) => g.fillText(DRUM_ROWS[p], W - 52, y0 + 12 + (k + 0.5) * rowH + 3)); }
    for (const n of t.notes_view) {
      if (n.end_s < S.scroll || n.start_s > t1) continue;
      const nx = x(n.start_s), w = isDrum ? 3 : Math.max(2, (n.end_s - n.start_s) * S.pxPerSec), ny = y0 + 12 + rowOf(n.pitch) * rowH - (isDrum ? rowH / 2 : 0);
      if (n.flags?.length && !isDrum) { g.strokeStyle = "rgba(128,137,149,.8)"; g.setLineDash([3, 2]); g.strokeRect(nx, ny, w, Math.max(2, rowH - 1)); g.setLineDash([]); continue; }
      g.globalAlpha = 0.25 + 0.75 * Math.min(1, n.confidence / 0.6);
      g.fillStyle = col; g.fillRect(nx, ny, w, Math.max(2, rowH - 1));
      g.globalAlpha = 1;
    }
    g.fillStyle = col; g.font = "600 10px -apple-system, sans-serif"; g.fillText(t.id.toUpperCase(), 8, y0 + 11);
  });
  // playhead
  const ph = x(now()); g.fillStyle = "#48ff91"; g.fillRect(ph, 0, 2, H);
  $("#timeOut").textContent = fmt(now());
  const bi = tv.beats.findLastIndex((b) => b <= now());
  if (bi >= 0) {
    const downsBefore = tv.beats.slice(0, bi + 1).filter((b) => tv.downs.has(b));
    const lastDown = downsBefore.length ? tv.beats.indexOf(downsBefore.at(-1)) : 0;
    $("#beatOut").textContent = `bar ${downsBefore.length} · beat ${bi - lastDown + 1}  (${tv.kind})`;
  }
}

loadProjects().then(async () => {
  // a step started before a page reload keeps running on the server: show it
  const jobs = await api("/api/jobs").catch(() => []);
  const running = jobs.filter((j) => j.state === "running").pop();
  if (running) { log("(resuming a step that was still running)"); watchJob(running.id, running.args[0]); }
});
new ResizeObserver(draw).observe($("#tlWrap"));
