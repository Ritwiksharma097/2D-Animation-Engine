// Animation workbench. Vanilla JS, no build step. Paths are relative to /workbench/.
"use strict";

const ASSETS = "../assets/", OUT = "../out/", ANN = "../annotations/";
const COL = { planted: "#1baf7a", free: "#eb6834", unknown: "#888", early: "#2a78d6", late: "#eb6834", slide: "#c81e28", ground: "#333" };
const STAGE_W = 1800;  // moving preview width in cell px
let manifest = null;
const viewers = [];
const params = new URLSearchParams(location.hash.slice(1));

function $(root, sel) { return root.querySelector(sel); }
function msg(t) { document.getElementById("msg").textContent = t; }
async function getJSON(url) { const r = await fetch(url, { cache: "no-store" }); if (!r.ok) throw new Error(r.status); return r.json(); }
function loadImage(src) { return new Promise((ok, bad) => { const i = new Image(); i.onload = () => ok(i); i.onerror = bad; i.src = src; }); }
const pad2 = n => String(n).padStart(2, "0");

// ---------------------------------------------------------------- viewer
class Viewer {
  constructor(el, initial) {
    this.el = el; this.cv = $(el, "canvas.view"); this.ctx = this.cv.getContext("2d");
    this.frames = []; this.seq = []; this.pos = 0; this.elapsed = 0; this.playing = false;
    this.worldX = 0; this.pins = {}; this.tintCache = new Map(); this.drag = null; this.dirty = false;
    this.bindControls();
    this.fillActions(initial);
  }

  get idx() { return this.seq[this.pos] ?? 0; }
  get frame() { return this.frames[this.idx]; }
  get zoom() { return parseFloat($(this.el, ".zoom").value); }
  get mode() { return $(this.el, ".mode").value; }
  get loopMode() { return $(this.el, ".loop-mode").value; }

  fillActions(initial) {
    const sel = $(this.el, ".sel-action");
    for (const [c, ch] of Object.entries(manifest.characters)) {
      const g = document.createElement("optgroup"); g.label = c;
      for (const [a, info] of Object.entries(ch.actions)) {
        const o = document.createElement("option"); o.value = `${c}/${a}`; o.textContent = `${c} / ${a}  [${info.status}]`; g.appendChild(o);
      }
      sel.appendChild(g);
    }
    sel.value = initial; sel.onchange = () => this.load(sel.value);
  }

  async load(key) {
    const [c, a] = key.split("/");
    this.char = c; this.action = a; this.info = manifest.characters[c].actions[a];
    $(this.el, ".sel-action").value = key;
    const st = $(this.el, ".status"); st.textContent = this.info.status; st.className = "status " + this.info.status;
    $(this.el, ".feedback").textContent = this.info.feedback || "";
    this.ann = null; this.report = null;
    if (!this.raw) try { this.ann = await getJSON(`${ANN}${c}/${a}.json`); } catch (e) { /* no annotations yet */ }
    if (this.raw) st.textContent += "  (original: annotations and edits ignored)";
    // the raw viewer needs the report of the unedited frames: analyze.py --no-annotations --tag original
    try { this.report = await getJSON(`${OUT}${c}/${a}${this.raw ? "__original" : ""}/report.json`); } catch (e) { /* not analysed yet */ }
    const defMs = this.ann?.default_duration_ms ?? Math.round(1000 / 12);
    const list = this.ann?.frames?.length ? this.ann.frames
      : Array.from({ length: this.info.frames }, (_, i) => ({ file: `${pad2(i + 1)}.png` }));
    const imgs = {};
    this.frames = await Promise.all(list.map(async f => ({
      file: f.file, duration_ms: f.duration_ms ?? defMs, contacts: structuredClone(f.contacts || {}), note: f.note,
      hold: f.hold || 1, drop: !!f.drop, offset: f.offset ? [...f.offset] : [0, 0], snap: f.snap_to_ground,
      img: await (imgs[f.file] ??= loadImage(`${ASSETS}${this.info.dir}/${f.file}`)),
    })));
    this.edits = { mirror: !!this.ann?.mirror, snap: !!this.ann?.snap_to_ground };
    this.scene = this.ann?.scene ? structuredClone(this.ann.scene) : null; this.sceneRes = null;
    this.baselines = {};
    $(this.el, ".loop-mode").value = this.ann?.loop_mode || (this.info.loop ? "loop" : "once");
    this.cell = this.info.cell_size || manifest.conventions.cell_size;
    this.groundY = this.ann?.ground_anchor?.y ?? this.info.ground_y ?? manifest.conventions.ground_y;
    const walk = this.report?.metrics?.walk;
    const t = this.ann?.travel;
    const tm = $(this.el, ".travel-mode"), tp = $(this.el, ".travel-px");
    if (t?.mode === "from_contacts") tm.value = "contacts";
    else if (t?.mode === "per_frame") tm.value = "perframe";
    else { tm.value = "constant"; tp.value = +(t?.px_per_frame ?? this.report?.settings?.travel_px_per_frame ?? walk?.recommended_travel_px ?? 12).toFixed(1); }
    $(this.el, ".all-ms").value = defMs;
    $(this.el, ".e-mirror").checked = this.edits.mirror; $(this.el, ".e-snap").checked = this.edits.snap;
    this.tintCache.clear(); this.dirty = false;
    this.rebuildSeq(); this.pos = 0; this.resetWorld();
    $(this.el, ".edits-note").textContent = this.ann?.edits_note || "";
    this.renderTimeline(); this.renderFlags(); this.renderContacts();
    this.syncSceneInputs(); if (this.scene) await this.checkScene(true);
    this.resize(); this.draw();
  }

  // ---------------- scene (props.py does the geometry; the page asks serve.py or reads the stored check)
  syncSceneInputs() {
    $(this.el, ".scene-row").style.display = this.scene ? "" : "none";
    const led = this.scene?.props?.find(p => p.type === "ledge"), lad = this.scene?.props?.find(p => p.type === "ladder");
    $(this.el, ".s-height").value = led ? +(this.scene.floor_y - led.top_y).toFixed(1) : "";
    $(this.el, ".s-front").value = led ? +led.front_x.toFixed(1) : ""; $(this.el, ".s-height").disabled = $(this.el, ".s-front").disabled = !led;
    $(this.el, ".s-rung").value = lad ? lad.rung_spacing : ""; $(this.el, ".s-rung").disabled = !lad;
  }

  async checkScene(initial) {
    try {
      const r = await fetch("/api/scene", { method: "POST", body: JSON.stringify(this.toDoc()) });
      const j = await r.json(); if (!r.ok) throw new Error(j.error);
      this.sceneRes = j;
    } catch (e) {
      try { this.sceneRes = await getJSON(`${OUT}${this.char}/${this.action}/scene_check.json`); if (!initial) msg("Live scene check needs serve.py; showing the stored check."); }
      catch (e2) { this.sceneRes = null; msg("No scene check: run python workbench/props.py " + `${this.char} ${this.action}`); }
    }
    $(this.el, ".scene-flags").textContent = (this.sceneRes?.flags || []).map(f => f.code + ": " + f.message).join("\n") || (this.sceneRes ? "no scene flags (not a pass)" : "");
    $(this.el, ".scene-flags").style.whiteSpace = "pre-line";
    this.resize(); this.draw();
  }

  sceneBox() {
    const fr = this.sceneRes.frames, [w, h] = this.cell;
    const x0 = Math.min(...fr.map(f => f.offset[0])) - 20, x1 = Math.max(...fr.map(f => f.offset[0])) + w + 20;
    const y0 = Math.min(...fr.map(f => f.offset[1])) - 20, y1 = this.scene.floor_y + 40;
    return { x0, y0, x1, y1, k: 900 / (x1 - x0) };
  }

  drawScene() {
    const ctx = this.ctx, b = this.sceneBox(), k = b.k;
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, this.cv.width, this.cv.height);
    ctx.setTransform(k, 0, 0, k, -b.x0 * k, -b.y0 * k);
    for (const [x0, y0, x1, y1] of this.sceneRes.solids) {
      const a0 = Math.max(x0, b.x0), a1 = Math.min(x1, b.x1), c0 = Math.max(y0, b.y0), c1 = Math.min(y1, b.y1);
      if (a0 < a1 && c0 < c1) { ctx.fillStyle = "#d6ccba"; ctx.fillRect(a0, c0, a1 - a0, c1 - c0); ctx.strokeStyle = "#968a6e"; ctx.lineWidth = 1 / k; ctx.strokeRect(a0, c0, a1 - a0, c1 - c0); }
    }
    for (const sfc of this.sceneRes.surfaces) if (sfc.kind.startsWith("ladder")) {
      ctx.strokeStyle = "#785a32"; ctx.lineWidth = (sfc.kind === "ladder_rail" ? 6 : 4) / k / 2;
      ctx.beginPath(); ctx.moveTo(...sfc.a); ctx.lineTo(...sfc.b); ctx.stroke();
    }
    const kept = [...new Set(this.seq)], pi = kept.indexOf(this.idx), fr = this.sceneRes.frames[pi];
    if (!fr) return;
    const t = this.xf(this.idx);
    ctx.save(); ctx.translate(fr.offset[0] + t.dx + (t.mirror ? this.cell[0] : 0), fr.offset[1] + t.dy); if (t.mirror) ctx.scale(-1, 1);
    ctx.drawImage(this.frame.img, 0, 0); ctx.restore();
    for (const c of fr.contacts) {
      const ok = c.dist !== null && c.dist <= 6, r = 6 / k;
      ctx.beginPath(); ctx.arc(c.world[0], c.world[1], r, 0, 7); ctx.lineWidth = 2 / k;
      if (c.state === "planted") { ctx.fillStyle = ok ? COL.planted : COL.slide; ctx.fill(); ctx.strokeStyle = "#000"; ctx.stroke(); }
      else { ctx.strokeStyle = COL.free; ctx.stroke(); }
      ctx.fillStyle = "#000"; ctx.font = `${12 / k}px system-ui`; ctx.fillText(`${c.name}${c.state === "planted" && !ok ? ` off ${c.dist}px` : ""}`, c.world[0] + 8 / k, c.world[1] - 8 / k);
    }
    for (const q of fr.clip_at || []) { ctx.strokeStyle = COL.slide; ctx.lineWidth = 3 / k; ctx.beginPath(); ctx.arc(q[0], q[1], 9 / k, 0, 7); ctx.stroke(); }
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = fr.clip_px || !Object.keys(fr.touching).length ? COL.slide : "#333"; ctx.font = "13px system-ui";
    ctx.fillText(`frame ${fr.frame}: ${fr.clip_px ? `clips ${fr.clip_px}px` : "no clipping"}; touching ${Object.keys(fr.touching).join(", ") || "NOTHING"}`, 8, 16);
  }

  rebuildSeq() {
    const kept = [...this.frames.keys()].filter(i => !this.frames[i].drop), n = kept.length;
    this.seq = kept.length ? [...kept] : [0];
    if (this.loopMode === "pingpong" && n > 2) for (let k = n - 2; k > 0; k--) this.seq.push(kept[k]);
    const sc = $(this.el, ".scrub"); sc.max = this.seq.length - 1;
    this.pos = Math.min(this.pos, this.seq.length - 1);
  }

  resetWorld() { this.worldX = this.sign > 0 ? 0 : STAGE_W - this.cell[0]; this.pins = {}; this.lastSlide = null; }

  // ---------------- edit layer (FORMAT.md "Edits"): mirror, then offset, then snap-to-ground
  get sign() { return this.edits?.mirror ? -1 : 1; }
  dur(i) { const f = this.frames[i]; return f.duration_ms * (f.hold || 1); }

  baseline(i) {
    const key = this.frames[i].file;
    if (!(key in this.baselines)) {
      const img = this.frames[i].img, c = document.createElement("canvas"); c.width = img.width; c.height = img.height;
      const x = c.getContext("2d"); x.drawImage(img, 0, 0);
      const a = x.getImageData(0, 0, c.width, c.height).data; let low = null;
      for (let y = c.height - 1; y >= 0 && low === null; y--) for (let xx = 0; xx < c.width; xx++) if (a[(y * c.width + xx) * 4 + 3] > 128) { low = y; break; }
      this.baselines[key] = low ?? this.groundY;
    }
    return this.baselines[key];
  }

  xf(i) {
    const f = this.frames[i];
    let dy = +f.offset[1] || 0;
    if (f.snap ?? this.edits.snap) {
      const feet = Object.entries(f.contacts).filter(([n, c]) => c.state === "planted" && (c.surface || "ground") === "ground" && /^(foot|toe|heel)_/.test(n));
      dy += this.groundY - (feet.length ? Math.max(...feet.map(([, c]) => c.y)) : this.baseline(i));
    }
    return { mirror: this.edits.mirror, dx: Math.round(+f.offset[0] || 0), dy: Math.round(dy) };
  }
  toView(i, c) { const t = this.xf(i); return { x: (t.mirror ? this.cell[0] - 1 - c.x : c.x) + t.dx, y: c.y + t.dy }; }
  fromView(i, p) { const t = this.xf(i), x = p.x - t.dx; return { x: t.mirror ? this.cell[0] - 1 - x : x, y: p.y - t.dy }; }
  drawFrame(ctx, i, img, ox) {
    const t = this.xf(i); ctx.save();
    ctx.translate(ox + t.dx + (t.mirror ? this.cell[0] : 0), t.dy); if (t.mirror) ctx.scale(-1, 1);
    ctx.drawImage(img, 0, 0); ctx.restore();
  }
  reportIndex(i) { const e = this.report?.entries; return e ? e.indexOf(i) : i; }

  // ---------------- travel
  travelFor(a, b) {
    const tm = $(this.el, ".travel-mode").value, walk = this.report?.metrics?.walk;
    let note = "";
    let v;
    if (tm === "constant") v = parseFloat($(this.el, ".travel-px").value) || 0;
    else if (tm === "best") { v = walk?.recommended_travel_px ?? 0; note = walk ? `${v.toFixed(1)} px/frame` : "no report"; }
    else if (tm === "perframe") {
      if (!walk) { v = 0; note = "no report"; }
      else {
        const ra = this.reportIndex(a), rb = this.reportIndex(b);
        const k = walk.steps.findIndex(([i, j]) => (i === ra && j === rb) || (i === rb && j === ra));
        v = k >= 0 ? (walk.recommended_per_frame_travel_px[k] ?? walk.recommended_travel_px) : walk.recommended_travel_px;
        note = "per-frame from report";
      }
    } else {
      const d = this.contactTravel(a, b);
      v = d.value; note = d.note;
    }
    $(this.el, ".travel-note").textContent = note;
    return v;
  }

  contactTravel(a, b) {
    // advance so that contacts planted in both frames stay fixed (FORMAT.md: from_contacts)
    const step = (i, j) => {
      const ds = [];
      for (const [name, c] of Object.entries(this.frames[i].contacts))
        if (c.state === "planted") {
          const d = this.frames[j].contacts[name];
          if (d && d.state === "planted" && (d.surface || "ground") === (c.surface || "ground"))
            ds.push(this.sign * (this.toView(i, c).x - this.toView(j, d).x));
        }
      return ds.length ? ds.reduce((s, x) => s + x, 0) / ds.length : null;
    };
    const v = step(a, b);
    if (v !== null) return { value: v, note: "from shared planted contact" };
    const all = [];
    const kept = this.seq.slice(0, [...new Set(this.seq)].length);
    for (let k = 0; k < kept.length; k++) { const w = step(kept[k], kept[(k + 1) % kept.length]); if (w !== null) all.push(w); }
    if (!all.length) return { value: 0, note: "no shared planted contacts annotated" };
    return { value: all.reduce((s, x) => s + x, 0) / all.length, note: "no shared contact on this step: mean used" };
  }

  // ---------------- playback
  setPlaying(p, fromSync) {
    this.playing = p; $(this.el, ".b-play").textContent = p ? "Pause" : "Play";
    if (p && this.loopMode === "once" && this.pos === this.seq.length - 1) { this.pos = 0; this.resetWorld(); }
    if (!fromSync && document.getElementById("syncPlay").checked)
      for (const v of viewers) if (v !== this && !v.el.classList.contains("hidden")) v.setPlaying(p, true);
  }

  advance(dir = 1) {
    const prev = this.idx, L = this.seq.length;
    let np = this.pos + dir;
    if (np >= L) { if (this.loopMode === "once") { this.setPlaying(false); return; } np = 0; }
    if (np < 0) np = this.loopMode === "once" ? 0 : L - 1;
    this.pos = np;
    if (this.mode === "moving") {
      const t = dir > 0 ? this.travelFor(prev, this.idx) : -this.travelFor(this.idx, prev);
      this.worldX += this.sign * t;
      if (this.worldX > STAGE_W - 520 || this.worldX < -200) { this.worldX = this.worldX > 0 ? -150 : STAGE_W - 600; this.pins = {}; }
      this.updatePins(prev);
    }
    this.elapsed = 0;
  }

  jump(pos) { this.pos = pos; this.elapsed = 0; this.resetWorld(); this.updatePins(null); this.syncUI(); this.draw(); }

  tick(dt) {
    if (!this.playing || !this.frames.length) return;
    this.elapsed += dt * parseFloat($(this.el, ".speed").value);
    let guard = 0;
    while (this.playing && this.elapsed >= this.dur(this.idx) && guard++ < 50) {
      const over = this.elapsed - this.dur(this.idx);
      this.advance(1); this.elapsed = over;
    }
    this.syncUI(); this.draw();
  }

  // contacts for a frame: annotated ones, else heuristic estimates from report.json
  contactsOf(i) {
    const ann = Object.entries(this.frames[i].contacts).map(([name, c]) => ({ name, ...c, ...this.toView(i, c), est: false }));
    if (ann.length) return ann;
    const fc = this.report?.metrics?.feet?.[this.reportIndex(i)]?.clusters || [];  // measured on edited frames already
    return fc.map((c, k) => ({ name: `est${k}`, x: c.x, y: c.y, state: c.planted ? "planted" : "free", est: true }));
  }

  updatePins(prevIdx) {
    const now = this.contactsOf(this.idx).filter(c => c.state === "planted");
    const old = this.pins; const pins = {};
    let worst = null;
    for (const c of now) {
      const wx = this.worldX + c.x;
      let pin = null;
      if (prevIdx !== null) {
        if (!c.est) pin = old[c.name];
        else { // heuristic: nearest previous pin
          let best = 1e9;
          for (const p of Object.values(old)) { const d = Math.abs(p.wx - wx); if (d < best && d < 60) { best = d; pin = p; } }
        }
      }
      pins[c.name] = pin ? { ...pin } : { wx, y: c.y };
      const s = wx - pins[c.name].wx;
      if (worst === null || Math.abs(s) > Math.abs(worst)) worst = s;
    }
    this.pins = pins; this.lastSlide = worst;
  }

  // ---------------- drawing
  resize() {
    if (this.mode === "scene" && this.sceneRes) { const b = this.sceneBox(); this.cv.width = 900; this.cv.height = Math.round((b.y1 - b.y0) * b.k); return; }
    const z = this.zoom;
    const w = this.mode === "moving" ? STAGE_W : this.cell[0];
    this.cv.width = Math.round(w * z); this.cv.height = Math.round(this.cell[1] * z);
  }

  tinted(i, colour) {
    const key = `${i}|${colour}`;
    if (!this.tintCache.has(key)) {
      const img = this.frames[i].img, c = document.createElement("canvas");
      c.width = img.width; c.height = img.height;
      const x = c.getContext("2d"); x.drawImage(img, 0, 0);
      x.globalCompositeOperation = "source-atop"; x.globalAlpha = 0.65; x.fillStyle = colour; x.fillRect(0, 0, c.width, c.height);
      this.tintCache.set(key, c);
    }
    return this.tintCache.get(key);
  }

  seqAt(offset) {
    const L = this.seq.length; let p = this.pos + offset;
    if (this.loopMode === "once") { if (p < 0 || p >= L) return null; }
    else p = ((p % L) + L) % L;
    return this.seq[p];
  }

  draw() {
    if (!this.frames.length) return;
    if (this.mode === "scene") { if (this.sceneRes) this.drawScene(); else if (!this.scene) msg("This action has no scene: add one with props.py."); return; }
    const ctx = this.ctx, z = this.zoom, moving = this.mode === "moving";
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, this.cv.width, this.cv.height);
    ctx.setTransform(z, 0, 0, z, 0, 0);
    const ox = moving ? this.worldX : 0;
    const gy = this.groundY;
    // ground
    ctx.strokeStyle = COL.ground; ctx.lineWidth = 2 / z;
    ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(this.cv.width / z, gy); ctx.stroke();
    ctx.fillStyle = "#666"; ctx.font = `${12 / z}px system-ui`;
    if (moving) {
      for (let x = 0; x < STAGE_W; x += 40) {
        ctx.beginPath(); ctx.moveTo(x, gy); ctx.lineTo(x, gy + (x % 200 ? 8 : 18)); ctx.stroke();
        if (x % 200 === 0) ctx.fillText(`${x}`, x + 3, gy + 30);
      }
    } else {
      ctx.setLineDash([6 / z, 6 / z]); ctx.strokeStyle = "#bbb";
      ctx.beginPath(); ctx.moveTo(this.cell[0] / 2, 0); ctx.lineTo(this.cell[0] / 2, this.cell[1]); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillText(`ground y=${gy}`, 6, gy - 6);
    }
    // onion skin (in place only; in moving mode it would need past world offsets)
    if (!moving) {
      const back = +$(this.el, ".onion-back").value, ahead = +$(this.el, ".onion-ahead").value, op = +$(this.el, ".onion-op").value / 100;
      for (let k = back; k >= 1; k--) { const i = this.seqAt(-k); if (i !== null) { ctx.globalAlpha = op * (1 - (k - 1) / (back + 1)); this.drawFrame(ctx, i, this.tinted(i, COL.early), 0); } }
      for (let k = ahead; k >= 1; k--) { const i = this.seqAt(k); if (i !== null) { ctx.globalAlpha = op * (1 - (k - 1) / (ahead + 1)); this.drawFrame(ctx, i, this.tinted(i, COL.late), 0); } }
      ctx.globalAlpha = 1;
    }
    this.drawFrame(ctx, this.idx, this.frame.img, ox);
    // contacts
    for (const c of this.contactsOf(this.idx)) {
      const x = ox + c.x, y = c.y, r = 7 / z;
      ctx.lineWidth = 2 / z;
      ctx.beginPath(); c.est ? ctx.rect(x - r, y - r, 2 * r, 2 * r) : ctx.arc(x, y, r, 0, 7);
      if (c.state === "planted" && !c.est) { ctx.fillStyle = COL.planted; ctx.fill(); ctx.strokeStyle = "#000"; ctx.stroke(); }
      else { ctx.strokeStyle = COL[c.state] || COL.unknown; ctx.stroke(); }
      ctx.fillStyle = "#000"; ctx.fillText(c.est ? "est" : c.name, x + 9 / z, y - 9 / z);
    }
    // pins + slide (moving)
    if (moving) {
      for (const [name, p] of Object.entries(this.pins)) {
        const c = this.contactsOf(this.idx).find(k => k.name === name); if (!c) continue;
        const wx = this.worldX + c.x, s = wx - p.wx;
        ctx.strokeStyle = COL.slide; ctx.fillStyle = COL.slide; ctx.lineWidth = 3 / z;
        ctx.beginPath(); ctx.moveTo(p.wx, gy + 4); ctx.lineTo(p.wx, gy - 14); ctx.stroke();
        if (Math.abs(s) > 0.5) {
          ctx.beginPath(); ctx.moveTo(p.wx, gy + 10 / z); ctx.lineTo(wx, gy + 10 / z); ctx.stroke();
          ctx.fillText(`slide ${Math.abs(s).toFixed(1)} px`, Math.min(p.wx, wx), gy - 24 / z);
        }
      }
    }
    const rd = $(this.el, ".slide-readout");
    rd.textContent = moving && this.lastSlide !== null ? `planted-foot slide since it landed: ${Math.abs(this.lastSlide).toFixed(1)} cell px` : "";
  }

  syncUI() {
    $(this.el, ".scrub").value = this.pos;
    const flags = this.flagsFor(this.idx);
    const f = this.frame;
    $(this.el, ".frame-label").textContent = `entry ${this.idx + 1}/${this.frames.length} (${f.file}, ${this.dur(this.idx)} ms${f.hold > 1 ? `, held x${f.hold}` : ""})${flags.length ? "  flags: " + flags.join(", ") : ""}`;
    $(this.el, ".e-dx").value = f.offset[0]; $(this.el, ".e-dy").value = f.offset[1];
    $(this.el, ".e-hold").value = f.hold; $(this.el, ".e-drop").checked = f.drop;
    $(this.el, ".e-snapinfo").textContent = (f.snap ?? this.edits.snap) ? `snap moves this frame ${this.xf(this.idx).dy - Math.round(+f.offset[1] || 0)} px` : "";
    for (const t of this.el.querySelectorAll(".tl")) t.classList.toggle("cur", +t.dataset.i === this.idx);
    this.renderContacts();
  }

  flagsFor(i) { const k = this.reportIndex(i); return k < 0 ? [] : (this.report?.flags || []).filter(f => f.frames.includes(k + 1)).map(f => f.code); }

  renderTimeline() {
    const tl = $(this.el, ".timeline"); tl.innerHTML = "";
    this.frames.forEach((f, i) => {
      const d = document.createElement("div"); d.className = "tl"; d.dataset.i = i;
      const c = document.createElement("canvas"); c.width = 116; c.height = 104;
      c.getContext("2d").drawImage(f.img, 0, 0, 116, 104);
      const n = document.createElement("div"); n.className = "n"; n.textContent = i + 1;
      const inp = document.createElement("input"); inp.type = "number"; inp.min = 10; inp.step = 10; inp.value = f.duration_ms; inp.title = "duration ms";
      inp.onchange = () => { f.duration_ms = Math.max(10, +inp.value); this.dirty = true; this.syncUI(); };
      inp.onclick = e => e.stopPropagation();
      if (f.drop) { d.style.opacity = 0.35; n.textContent += " dropped"; }
      if (f.hold > 1) n.textContent += ` x${f.hold}`;
      d.append(c, n, inp);
      const fl = this.flagsFor(i);
      if (fl.length) { const dot = document.createElement("span"); dot.className = "flagdot"; dot.title = fl.join(", "); d.appendChild(dot); }
      d.onclick = () => { this.setPlaying(false); this.jump(this.seq.indexOf(i)); };
      tl.appendChild(d);
    });
    this.syncUI();
  }

  renderFlags() {
    const box = $(this.el, ".flags"); box.innerHTML = "";
    const r = this.report;
    $(this.el, ".summary").textContent = r ? r.summary : "No report.json yet: run  python workbench/analyze.py " + `${this.char} ${this.action}` + (this.raw ? " --no-annotations --tag original" : "");
    for (const f of r?.flags || []) {
      const d = document.createElement("div"); d.className = "flag";
      d.innerHTML = `<code>${f.code}</code> ${f.frames.length ? "[" + f.frames.join(",") + "] " : ""}`;
      d.appendChild(document.createTextNode(f.message));
      const entry = this.report.entries ? this.report.entries[f.frames[0] - 1] : f.frames[0] - 1;
      if (f.frames.length) d.onclick = () => { this.setPlaying(false); this.jump(Math.max(0, this.seq.indexOf(entry))); };
      box.appendChild(d);
    }
  }

  renderContacts() {
    const t = $(this.el, "table.contacts"); if (!this.frame) return;
    t.innerHTML = "";
    const cs = this.frame.contacts;
    if (!Object.keys(cs).length) { t.innerHTML = `<tr><td style="color:#888">none annotated${this.report ? " (squares = heuristic estimates)" : ""}</td></tr>`; return; }
    for (const [name, c] of Object.entries(cs)) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${name}</td><td>x ${(+c.x).toFixed(0)}, y ${(+c.y).toFixed(0)}${c.surface ? " on " + c.surface : ""}</td>`;
      const td = document.createElement("td"), sel = document.createElement("select");
      for (const s of ["planted", "free", "unknown"]) sel.add(new Option(s, s, false, s === c.state));
      sel.onchange = () => { c.state = sel.value; this.dirty = true; this.draw(); };
      td.appendChild(sel);
      const del = document.createElement("button"); del.textContent = "delete";
      del.onclick = () => { delete cs[name]; this.dirty = true; this.renderContacts(); this.draw(); };
      const td2 = document.createElement("td"); td2.appendChild(del);
      tr.append(td, td2); t.appendChild(tr);
    }
  }

  // ---------------- editing
  cellPoint(e) {
    const r = this.cv.getBoundingClientRect();
    const sx = this.cv.width / r.width;
    return { x: (e.clientX - r.left) * sx / this.zoom - (this.mode === "moving" ? this.worldX : 0), y: (e.clientY - r.top) * sx / this.zoom };
  }

  nearest(p, maxd) {
    let best = null, bd = maxd;
    for (const [name, c] of Object.entries(this.frame.contacts)) { const v = this.toView(this.idx, c), d = Math.hypot(v.x - p.x, v.y - p.y); if (d < bd) { bd = d; best = name; } }
    return best;
  }

  onDown(e) {
    if (this.mode !== "inplace") { msg("Switch to the in-place preview to edit contacts."); return; }
    const surf = $(this.el, ".c-surface").value;
    this.setPlaying(false);
    const p = this.cellPoint(e);
    const near = this.nearest(p, 14 / this.zoom);
    if (e.shiftKey) { if (near) { delete this.frame.contacts[near]; this.dirty = true; } }
    else if (near) this.drag = near;
    else {
      const name = $(this.el, ".c-custom").value.trim() || $(this.el, ".c-name").value;
      const q = this.fromView(this.idx, p);
      this.frame.contacts[name] = { x: +q.x.toFixed(1), y: +q.y.toFixed(1), state: $(this.el, ".c-state").value, surface: surf };
      this.drag = name; this.dirty = true;
    }
    this.renderContacts(); this.draw();
  }

  onMove(e) {
    if (!this.drag) return;
    const p = this.fromView(this.idx, this.cellPoint(e)), c = this.frame.contacts[this.drag];
    c.x = +p.x.toFixed(1); c.y = +p.y.toFixed(1); this.dirty = true; this.draw();
  }

  toDoc() {
    const tm = $(this.el, ".travel-mode").value, walk = this.report?.metrics?.walk;
    let travel;
    if (tm === "constant") travel = { mode: "constant", px_per_frame: parseFloat($(this.el, ".travel-px").value) || 0 };
    else if (tm === "best" && walk) travel = { mode: "constant", px_per_frame: walk.recommended_travel_px };
    else if (tm === "perframe" && walk) travel = { mode: "per_frame", px_per_frame: walk.recommended_per_frame_travel_px };
    else travel = { mode: "from_contacts" };
    const extra = { ...(this.ann || {}) };
    delete extra.mirror; delete extra.snap_to_ground;
    return {
      ...extra,
      ...(this.edits.mirror ? { mirror: true } : {}), ...(this.edits.snap ? { snap_to_ground: true } : {}),
      ...(this.scene ? { scene: this.scene } : {}),
      format: "workbench-action/1", character: this.char, action: this.action, source_dir: this.info.dir,
      cell_size: this.cell, loop_mode: this.loopMode,
      default_duration_ms: +$(this.el, ".all-ms").value || 83, ground_anchor: { y: this.groundY }, facing: "right", travel,
      frames: this.frames.map(f => {
        const o = { file: f.file, duration_ms: f.duration_ms };
        if (Object.keys(f.contacts).length) o.contacts = f.contacts;
        if (f.hold > 1) o.hold = f.hold;
        if (f.drop) o.drop = true;
        if (+f.offset[0] || +f.offset[1]) o.offset = [+f.offset[0], +f.offset[1]];
        if (f.snap !== undefined) o.snap_to_ground = f.snap;
        if (f.note) o.note = f.note;
        return o;
      }),
    };
  }

  download() {
    const blob = new Blob([JSON.stringify(this.toDoc(), null, 1)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${this.action}.json`; a.click();
    msg(`Downloaded ${this.action}.json - put it in annotations/${this.char}/`);
  }

  async save() {
    try {
      const r = await fetch(`${ANN}${this.char}/${this.action}.json`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(this.toDoc()) });
      if (!r.ok) throw new Error(r.status);
      this.dirty = false; msg(`Saved annotations/${this.char}/${this.action}.json`);
    } catch (e) { msg("Save needs workbench/serve.py (plain http.server is read-only); downloading instead."); this.download(); }
  }

  async reanalyze() {
    try {
      const r = await fetch(`/api/analyze?character=${this.char}&action=${this.action}`, { method: "POST" });
      if (!r.ok) throw new Error(r.status);
      this.report = await getJSON(`${OUT}${this.char}/${this.action}/report.json`);
      this.renderFlags(); this.renderTimeline(); this.draw(); msg("Analysis updated.");
    } catch (e) { msg("Re-run needs workbench/serve.py. Otherwise run analyze.py yourself and reload."); }
  }

  bindControls() {
    const el = this.el, on = (s, ev, f) => $(el, s).addEventListener(ev, f);
    on(".b-play", "click", () => this.setPlaying(!this.playing));
    on(".b-next", "click", () => { this.setPlaying(false); this.advance(1); this.syncUI(); this.draw(); });
    on(".b-prev", "click", () => { this.setPlaying(false); this.advance(-1); this.syncUI(); this.draw(); });
    on(".scrub", "input", e => { this.setPlaying(false); this.jump(+e.target.value); });
    on(".loop-mode", "change", () => { this.rebuildSeq(); this.dirty = true; this.syncUI(); this.draw(); });
    on(".b-all-ms", "click", () => { const v = Math.max(10, +$(el, ".all-ms").value); this.frames.forEach(f => f.duration_ms = v); this.dirty = true; this.renderTimeline(); });
    for (const s of [".zoom", ".mode"]) on(s, "change", () => { this.resize(); this.resetWorld(); this.updatePins(null); this.draw(); });
    for (const s of [".onion-back", ".onion-ahead", ".onion-op"]) on(s, "input", () => this.draw());
    for (const s of [".travel-mode", ".travel-px"]) on(s, "change", () => { $(el, ".travel-px").disabled = $(el, ".travel-mode").value !== "constant"; this.resetWorld(); this.travelFor(this.idx, this.idx); this.draw(); });
    this.cv.addEventListener("mousedown", e => this.onDown(e));
    window.addEventListener("mousemove", e => this.onMove(e));
    window.addEventListener("mouseup", () => { if (this.drag) { this.drag = null; this.renderContacts(); } });
    on(".b-copy-prev", "click", () => {
      const prev = this.seqAt(-1); if (prev === null) return;
      this.frame.contacts = structuredClone(this.frames[prev].contacts); this.dirty = true; this.renderContacts(); this.draw();
    });
    on(".b-save", "click", () => this.save());
    on(".b-download", "click", () => this.download());
    on(".b-analyze", "click", () => this.reanalyze());
    const edited = () => { this.dirty = true; this.rebuildSeq(); this.renderTimeline(); this.resetWorld(); this.draw(); };
    on(".e-dx", "change", e => { this.frame.offset[0] = +e.target.value || 0; edited(); });
    on(".e-dy", "change", e => { this.frame.offset[1] = +e.target.value || 0; edited(); });
    on(".e-hold", "change", e => { this.frame.hold = Math.max(1, Math.round(+e.target.value || 1)); edited(); });
    on(".e-drop", "change", e => { this.frame.drop = e.target.checked; edited(); });
    on(".e-mirror", "change", e => { this.edits.mirror = e.target.checked; this.tintCache.clear(); edited(); });
    on(".e-snap", "change", e => { this.edits.snap = e.target.checked; edited(); });
    const sceneEdit = () => {
      const led = this.scene?.props?.find(p => p.type === "ledge"), lad = this.scene?.props?.find(p => p.type === "ladder");
      if (led) { led.top_y = this.scene.floor_y - (+$(el, ".s-height").value); const w = led.back_x - led.front_x; led.front_x = +$(el, ".s-front").value; led.back_x = led.front_x + w; }
      if (lad) lad.rung_spacing = Math.max(5, +$(el, ".s-rung").value);
      this.dirty = true; this.checkScene();
    };
    for (const s of [".s-height", ".s-front", ".s-rung"]) on(s, "change", sceneEdit);
    on(".b-scene", "click", () => this.checkScene());
    on(".b-suggest", "click", async () => {
      try {
        const r = await fetch(`/api/suggest-idle?character=${this.char}&action=${this.action}`, { method: "POST" });
        const j = await r.json(); if (!r.ok) throw new Error(j.error);
        await this.load(`${this.char}/${this.action}`); msg("Idle holds suggested and saved: " + j.summary);
      } catch (e) { msg("Suggest needs workbench/serve.py: " + e.message + "  (CLI: python workbench/edits.py suggest-idle " + `${this.char} ${this.action} --write)`); }
    });
  }
}

// ---------------------------------------------------------------- page
function applyParams(v, prefix) {
  const g = k => params.get(prefix + k) ?? params.get(k);
  if (g("mode")) $(v.el, ".mode").value = g("mode");
  if (g("travel")) { $(v.el, ".travel-mode").value = "constant"; $(v.el, ".travel-px").value = g("travel"); }
  if (g("travelmode")) $(v.el, ".travel-mode").value = g("travelmode");
  if (g("onion")) { const [b, a] = g("onion").split(","); $(v.el, ".onion-back").value = b; $(v.el, ".onion-ahead").value = a ?? 0; }
  if (g("zoom")) $(v.el, ".zoom").value = g("zoom");
  if (g("loop")) { $(v.el, ".loop-mode").value = g("loop"); v.rebuildSeq(); }
  v.resize(); v.resetWorld();
  const steps = +(g("steps") || 0);           // advance N frames (useful for screenshots of the moving preview)
  if (g("frame")) v.jump(v.seq.indexOf(+g("frame") - 1));
  for (let k = 0; k < steps; k++) v.advance(1);
  v.syncUI(); v.draw();
}

async function init() {
  manifest = await getJSON(`${ASSETS}manifest.json`);
  const main = document.getElementById("main"), tpl = document.getElementById("viewerTpl");
  const mk = async (initial, hidden, prefix) => {
    const el = tpl.content.firstElementChild.cloneNode(true); if (hidden) el.classList.add("hidden");
    main.appendChild(el);
    const v = new Viewer(el, initial); viewers.push(v);
    v.raw = params.get(prefix + "raw") === "1";
    await v.load(initial); applyParams(v, prefix); return v;
  };
  await mk(params.get("a") || "guard/walk", false, "a.");
  const b = await mk(params.get("b") || "ren/walk_keypose", !params.get("b"), "b.");
  const cb = document.getElementById("compareBtn");
  const setCmp = on => { b.el.classList.toggle("hidden", !on); cb.classList.toggle("on", on); b.resize(); b.draw(); };
  cb.onclick = () => setCmp(b.el.classList.contains("hidden"));
  setCmp(!!params.get("b"));
  if (params.get("play")) viewers[0].setPlaying(true);
  let last = performance.now();
  const loop = now => { const dt = now - last; last = now; for (const v of viewers) v.tick(dt); requestAnimationFrame(loop); };
  requestAnimationFrame(loop);
  window.addEventListener("keydown", e => {
    if (["INPUT", "SELECT"].includes(e.target.tagName)) return;
    const v = viewers[0];
    if (e.code === "Space") { e.preventDefault(); v.setPlaying(!v.playing); }
    if (e.code === "ArrowRight") { v.setPlaying(false); v.advance(1); v.syncUI(); v.draw(); }
    if (e.code === "ArrowLeft") { v.setPlaying(false); v.advance(-1); v.syncUI(); v.draw(); }
  });
  window.addEventListener("beforeunload", e => { if (viewers.some(v => v.dirty)) { e.preventDefault(); e.returnValue = ""; } });
  window.workbench = { viewers };  // for tests / screenshots
  document.body.dataset.ready = "1";
}

init().catch(e => { msg("Failed to start: " + e); console.error(e); });
