// Animation runtime for workbench exports. Vanilla ES module, no build step, no DOM needed for the logic
// (loading and drawing use fetch/Image/canvas only when called). API: runtime/README.md.

// ------------------------------------------------------------------ clips

/** Wrap an export JSON (workbench-export/1) as a clip. `img` may be null (tests, headless). */
export function makeClip(key, json, img = null) {
  if (json.format !== "workbench-export/1") throw new Error(`${key}: not a workbench export`);
  return { key, ...json, img, scale: json.scale ?? 1 };
}

/** Load `<base>/<character>/<action>.json` and its sheet. */
export async function loadClip(base, key) {
  const j = await (await fetch(`${base}/${key}.json`)).json();
  const img = await loadImage(`${base}/${key.split("/")[0]}/${j.image}`);
  return makeClip(key, j, img);
}

/**
 * Load an image and always settle. Waits for `onload` (which fires in background tabs, unlike `img.decode()`, which may
 * never resolve while the window isn't drawn), retries on error or timeout with a cache-busting query, then rejects.
 */
export function loadImage(src, { timeoutMs = 10000, retries = 2 } = {}) {
  return new Promise((resolve, reject) => {
    let attempt = 0;
    const go = () => {
      const img = new Image(); let settled = false, timer = null;
      const ok = () => { if (settled) return; settled = true; clearTimeout(timer); resolve(img); };
      const fail = why => {
        if (settled) return; settled = true; clearTimeout(timer);
        if (attempt++ < retries) go(); else reject(new Error(`could not load ${src}: ${why}`));
      };
      img.onload = ok; img.onerror = () => fail("error");
      timer = setTimeout(() => (img.complete && img.naturalWidth ? ok() : fail("timeout")), timeoutMs);
      img.src = attempt ? `${src}${src.includes("?") ? "&" : "?"}retry=${attempt}` : src;
      if (img.complete && img.naturalWidth) ok();
    };
    go();
  });
}

/** Load several clips; `onProgress(loaded, total, key)` is called as each finishes (for a preload bar). */
export async function loadClips(base, keys, onProgress = null) {
  const out = {}; let done = 0;
  onProgress?.(0, keys.length, null);
  await Promise.all(keys.map(async k => { out[k] = await loadClip(base, k); onProgress?.(++done, keys.length, k); }));
  return out;
}

/**
 * Crisp canvas at any devicePixelRatio: the backing store is CSS size x DPR, drawing stays in logical units (w x h).
 * Returns a view with reset(ctx) (logical transform) and toLogical(clientX, clientY). Call again on resize.
 */
export function fitCanvas(canvas, w, h, dpr = globalThis.devicePixelRatio || 1) {
  const cssW = canvas.getBoundingClientRect().width || w;
  canvas.width = Math.round(cssW * dpr); canvas.height = Math.round(cssW * dpr * h / w);
  const k = canvas.width / w;
  return {
    w, h, k, dpr,
    reset(ctx) { ctx.setTransform(k, 0, 0, k, 0, 0); },
    toLogical(cx, cy) { const r = canvas.getBoundingClientRect(); return { x: (cx - r.left) * w / r.width, y: (cy - r.top) * h / r.height }; },
  };
}

/** Fixed-timestep stepper: positions depend only on elapsed time, not on the display's frame rate. */
export function makeStepper(update, stepMs = 1000 / 240, maxFrameMs = 250) {
  let acc = 0;
  return dt => { acc += Math.min(maxFrameMs, dt); let n = 0; while (acc >= stepMs - 1e-9) { update(stepMs); acc -= stepMs; n++; } return n; };
}

/** Furthest pixel ahead of the anchor over all frames (game px), used to stop before solids. */
export function frontExtent(clip) {
  return Math.max(...clip.frames.map(f => f.offset[0] + f.rect[2] - clip.anchor[0])) * clip.scale;
}

// ------------------------------------------------------------------ ledge-height adapter (workbench step 13)

/**
 * Pick the climb path for a ledge `heightGame` game px high. Returns {ok, pct, entry, path, reason}.
 * Refuses heights outside the export's looser range (`strict: true` = only the strict range).
 */
export function adaptClimb(clip, heightGame, { strict = false } = {}) {
  const by = clip.paths_by_height;
  if (!by) return { ok: false, reason: `${clip.key} has no paths_by_height` };
  const base = by["100"].height * clip.scale;
  const pct = Math.round(100 * heightGame / base);
  const entry = by[String(pct)];
  if (!entry) return { ok: false, pct, reason: `ledge ${pct}% of the original is outside the exported 60-140%` };
  const ok = strict ? entry.supported : entry.supported_2x;
  const r = clip.height_rule || {};
  if (!ok) return { ok: false, pct, entry, reason: `ledge ${pct}% is outside the supported range (${(strict ? r.strict_range_pct : r.loose_range_pct)?.join("-")}%): these drawings need a different climb` };
  return { ok: true, pct, entry, path: pct === 100 && clip.path ? clip.path : entry.path, marginal: !entry.supported };
}

// ------------------------------------------------------------------ world

/**
 * A side-view world: one floor plus platforms (ledges). Platforms are {id, x0, x1, top}; x0 is the front face.
 * Characters on the floor stop before a platform face; on a platform they stop at its edges.
 */
export class World {
  constructor({ floorY, floors = null, platforms = [], ladders = [], frontBandCell = 40 }) {
    this.bodies = [];   // characters with a `radius` register here so they don't walk through each other
    // floors: walk regions [{id, x0, x1, y, left: "face"|"edge", right: "face"|"edge"}] (see runtime/level.js);
    // without them there is one endless floor called "floor" at floorY (the single-screen demos).
    this.floors = floors; this.floorY = floorY ?? floors?.[0]?.y; this.platforms = platforms; this.ladders = ladders; this.frontBandCell = frontBandCell;
  }
  region(id) { return this.floors?.find(f => f.id === id); }
  /** The nearest other body ahead of `ch` (same surface, both standing or walking) closer than the two radii plus `adv`. */
  bodyAhead(ch, adv) {
    if (!ch.radius || ch.passable) return null;
    let best = null;
    for (const b of this.bodies) {
      if (b === ch || !b.radius || b.passable || b.surface !== ch.surface || b.state === "climb" || b.state === "ladder" || b.state === "jump") continue;
      const ahead = ch.dir * (b.x - ch.x);
      if (ahead > 0 && ahead - adv < ch.radius + b.radius && (!best || ahead < best.ahead)) best = { body: b, ahead };
    }
    return best;
  }
  /** y of the floor a platform stands on. */
  baseY(p) { return p.base ?? this.floorY; }
  /** Ladders: {id, x, top, rungSpacing, toSurface}; rungs every rungSpacing up from the floor. */
  ladder(id) { return this.ladders.find(l => l.id === id); }
  platform(id) { return this.platforms.find(p => p.id === id); }
  surfaceY(surface) {
    if (surface === "floor") return this.floorY;
    const f = this.region(surface); if (f) return f.y;
    return this.platform(surface).top;
  }
  /** Walking limits [min, max] for a character on `surface` with walk clip `walk`, currently at x. */
  limits(surface, walk, x) {
    const fe = frontExtent(walk), band = this.frontBandCell * walk.scale;
    const f = this.region(surface);
    if (f) return [f.left === "face" ? f.x0 - band + fe : f.x0 + 10, f.right === "face" ? f.x1 + band - fe : f.x1 - 10];
    if (surface !== "floor") { const p = this.platform(surface); return [p.x0 + 10, p.x1 - 10]; }
    let lo = -Infinity, hi = Infinity;
    for (const p of this.platforms) {
      if (p.x0 >= x) hi = Math.min(hi, p.x0 + band - fe);   // stop before the face (a near limb may overlap 40 cell px)
      else if (p.x1 <= x) lo = Math.max(lo, p.x1 - band + fe);
    }
    return [lo, hi];
  }
}

// ------------------------------------------------------------------ character state machine

/**
 * States: idle, walk, turn, climb, jump, play (one-shot reaction), wait. Commands queue; when the queue is empty the
 * character returns to idle. Events: "state" {from,to}, "frame" {clip,frame}, "done" {command}, "refused" {command,reason},
 * named clip events (export `events`, e.g. "pickup", "bite", "takeoff") {clip, frame, point}.
 */
export class Character {
  constructor({ id, clips, world, x, surface = "floor", dir = 1, names = {}, turnMs = 120, radius = 0 }) {
    this.id = id; this.clips = clips; this.world = world; this.x = x; this.surface = surface; this.dir = dir;
    this.names = { idle: "idle", walk: "walk", climb_up: "climb_up", climb_down: "climb_down", jump: "jump", ladder: "ladder", ...names };
    this.y = world.surfaceY(surface); this.turnMs = turnMs;
    this.queue = []; this.cmd = null; this.state = "idle"; this.clip = this.c("idle"); this.k = 0; this.t = 0;
    this.pins = {}; this.drift = 0; this.maxDrift = 0; this.handlers = {}; this.travelOverride = null; this.rungError = 0;
    this.radius = radius; if (radius) world.bodies.push(this);   // radius > 0: other bodies stop instead of walking through
  }
  c(role) { const k = this.names[role] ?? role, c = this.clips[k]; if (!c) throw new Error(`${this.id}: no clip for ${role} (${k})`); return c; }
  on(evt, fn) { (this.handlers[evt] ??= []).push(fn); return this; }
  emit(evt, data = {}) { for (const fn of this.handlers[evt] || []) fn({ character: this, ...data }); }

  // --- commands (chainable); they run in order
  walkTo(x) { this.queue.push({ type: "walk", x }); return this; }
  turn(dir) { this.queue.push({ type: "turn", dir }); return this; }
  climbUp(platformId, opts = {}) { this.queue.push({ type: "climb_up", platform: platformId, ...opts }); return this; }
  climbDown(platformId, opts = {}) { this.queue.push({ type: "climb_down", platform: platformId, ...opts }); return this; }
  /** Walk to the ladder, get on (a cut: no get-on drawings), loop the climb a whole number of cycles, get off on top (a cut). */
  climbLadder(ladderId) { const l = this.world.ladder(ladderId); this.queue.push({ type: "walk", x: l.x }, { type: "ladder", ladder: ladderId }); return this; }
  jumpTo(x, surface) { this.queue.push({ type: "jump", x, surface }); return this; }
  play(role, { loops = 1 } = {}) { this.queue.push({ type: "play", role, loops }); return this; }
  wait(ms) { this.queue.push({ type: "wait", ms }); return this; }
  /** Play `frames` (0-based, default all) of a role's clip, then hold the last one until the next command (e.g. a crouch). */
  pose(role, { frames = null, tag = null } = {}) { this.queue.push({ type: "pose", role, frames, tag }); return this; }
  /** Holding a pose (finished its frames, waiting for the next command). */
  get holding() { return this.state === "pose" && !!this.cmd?.held; }
  clear() { this.queue = []; return this; }
  get busy() { return (this.state !== "idle" && !this.holding) || this.queue.length > 0; }

  setState(s, clip) {
    const from = this.state; this.state = s; if (clip) { this.clip = clip; this.k = 0; this.t = 0; this.enterFrame(); }
    if (from !== s) this.emit("state", { from, to: s });
  }

  /** Start the next command, or go idle. */
  next() {
    if (this.cmd) this.emit("done", { command: this.cmd });
    this.cmd = this.queue.shift() ?? null;
    this.pins = {};
    const cmd = this.cmd;
    if (!cmd) return this.setState("idle", this.c("idle"));
    if (cmd.type === "walk") {
      const want = cmd.x >= this.x ? 1 : -1;
      if (want !== this.dir) { this.queue.unshift(cmd); this.cmd = { type: "turn", dir: want, auto: true }; return this.startTurn(); }
      const [lo, hi] = this.world.limits(this.surface, this.c("walk"), this.x);
      cmd.goal = Math.max(lo, Math.min(hi, cmd.x));
      if (Math.abs(cmd.goal - this.x) < 1) return this.next();
      this.setState("walk", this.c("walk")); this.updatePins();
    } else if (cmd.type === "turn") {
      if (cmd.dir === this.dir) return this.next();
      this.startTurn();
    } else if (cmd.type === "climb_up" || cmd.type === "climb_down") {
      const clip = this.c(cmd.type), p = this.world.platform(cmd.platform);
      const base = this.world.baseY(p), height = base - p.top;
      const a = adaptClimb(clip, height, cmd);
      if (!a.ok) { this.emit("refused", { command: cmd, reason: a.reason }); this.queue = []; return this.next(); }
      cmd.path = a.path; cmd.marginal = a.marginal; cmd.base = base;
      // drawings are placed relative to the ledge face: start exactly there (a visible step if the walk had to stop short).
      // side "back" climbs the far face mirrored (facing left).
      const dir = cmd.side === "back" ? -1 : 1;
      const sx = dir > 0 ? p.x0 - a.entry.front_x * clip.scale : p.x1 + a.entry.front_x * clip.scale;
      cmd.stepIn = sx - this.x; this.x = sx; this.dir = dir; cmd.dir = dir;
      this.y = cmd.type === "climb_up" ? base : p.top;
      cmd.start = { x: this.x, y: this.y };
      this.setState("climb", clip);
    } else if (cmd.type === "ladder") {
      const clip = this.c("ladder"), l = this.world.ladder(cmd.ladder), L = clip.ladder;
      if (!L) { this.emit("refused", { command: cmd, reason: `${clip.key} has no ladder block` }); this.queue = []; return this.next(); }
      const bottom = this.world.surfaceY(l.from ?? "floor");
      const perCycle = L.rise_px_per_cycle * clip.scale, height = bottom - l.top;
      cmd.cycles = Math.max(1, Math.round(height / perCycle));
      cmd.leftover = height - cmd.cycles * perCycle;
      cmd.frames = cmd.cycles * clip.frames.length; cmd.done = 0;
      this.x = l.x; this.y = bottom; this.dir = 1; cmd.bottom = bottom;
      this.emit("ladder_on", { ladder: l.id, cycles: cmd.cycles, assumedRise: !!L.rise_assumed });
      this.setState("ladder", clip); this.rungError = this.measureRungs(l);
    } else if (cmd.type === "jump") {
      const clip = this.c("jump");
      if (!clip.jump) { this.emit("refused", { command: cmd, reason: "jump clip has no jump timing" }); return this.next(); }
      this.dir = cmd.x >= this.x ? 1 : -1; cmd.start = { x: this.x, y: this.y };
      cmd.landY = this.world.surfaceY(cmd.surface);
      this.setState("jump", clip);
    } else if (cmd.type === "play") {
      cmd.left = cmd.loops; this.setState("play", this.c(cmd.role));
    } else if (cmd.type === "wait") {
      cmd.left = cmd.ms; this.setState("wait", this.c("idle"));
    } else if (cmd.type === "pose") {
      const clip = this.c(cmd.role);
      cmd.frames ??= clip.frames.map((_, i) => i); cmd.i = 0; cmd.held = cmd.frames.length <= 1;
      this.setState("pose", clip); if (cmd.frames[0] !== 0) { this.k = cmd.frames[0]; this.enterFrame(); }
    }
  }

  /** Where a climb on platform `platformId` starts (x), or null when the ledge height is refused. */
  climbStartX(role, platformId, side = "front") {
    const clip = this.c(role), p = this.world.platform(platformId), a = adaptClimb(clip, this.world.baseY(p) - p.top);
    if (!a.ok) return null;
    return side === "back" ? p.x1 + a.entry.front_x * clip.scale : p.x0 - a.entry.front_x * clip.scale;
  }
  /** Where a climb ends (x), relative to the same start rule. */
  climbEndX(role, platformId, side = "front") {
    const clip = this.c(role), p = this.world.platform(platformId), a = adaptClimb(clip, this.world.baseY(p) - p.top);
    if (!a.ok) return null;
    const last = a.path[a.path.length - 1], dir = side === "back" ? -1 : 1;
    return this.climbStartX(role, platformId, side) + dir * last[0] * clip.scale;
  }

  startTurn() { this.turnLeft = this.turnMs; this.setState("turn"); }

  enterFrame() {
    this.emit("frame", { clip: this.clip.key, frame: this.k });
    for (const [name, e] of Object.entries(this.clip.events || {}))
      if (e.frame === this.k) this.emit(name, { clip: this.clip.key, frame: this.k, point: e.point && this.toWorld({ x: e.point[0], y: e.point[1] }) });
  }

  toWorld(c, clip = this.clip) { return { x: this.x + this.dir * (c.x - clip.anchor[0]) * clip.scale, y: this.y + (c.y - clip.anchor[1]) * clip.scale }; }

  updatePins() {
    const now = {}; let worst = 0;
    for (const [n, c] of Object.entries(this.clip.frames[this.k].contacts || {})) {
      if (c.state !== "planted") continue;
      const w = this.toWorld(c);
      now[n] = this.pins[n] ?? w;
      worst = Math.max(worst, Math.abs(w.x - now[n].x));
    }
    this.pins = now; this.drift = worst; this.maxDrift = Math.max(this.maxDrift, worst);
  }

  /** Largest distance (game px) from a planted rung contact to the nearest rung. */
  measureRungs(l) {
    let worst = 0;
    for (const c of Object.values(this.clip.frames[this.k].contacts || {})) {
      if (c.state !== "planted" || c.surface !== "ladder_rung") continue;
      const w = this.toWorld(c), r = (this.world.surfaceY(l.from ?? "floor") - w.y) / l.rungSpacing;
      worst = Math.max(worst, Math.abs(r - Math.round(r)) * l.rungSpacing);
    }
    return worst;
  }

  /** True while walking on a clip whose travel is an override from settings and the planted feet have drifted. */
  get overrideSliding() { return !!(this.clip.travel_override || this.travelOverride !== null) && this.drift > 0.5; }

  stepTravel() {
    const f = this.clip.frames[this.k];
    return (this.travelOverride ?? f.travel_px) * this.clip.scale;
  }

  /** Advance by dt milliseconds. */
  update(dt) {
    if ((this.state === "idle" && !this.cmd || this.holding) && this.queue.length) return this.next();
    if (this.holding) return;
    if (this.state === "turn") {
      this.turnLeft -= dt;
      if (this.turnLeft <= 0) { this.dir = -this.dir; this.emit("turn", { dir: this.dir }); this.next(); }
      return;
    }
    if (this.state === "wait") { this.cmd.left -= dt; if (this.cmd.left <= 0) this.next(); }
    const clip = this.clip;
    this.t += dt;
    let guard = 0;
    while (this.t >= clip.frames[this.k].duration_ms && guard++ < 50) {
      this.t -= clip.frames[this.k].duration_ms;
      if (this.advance() === "stop") return;
    }
  }

  /** One frame boundary. Returns "stop" when the state changed. */
  advance() {
    const clip = this.clip, n = clip.frames.length, cmd = this.cmd;
    if (this.state === "idle" || this.state === "wait") { this.k = (this.k + 1) % n; this.enterFrame(); return; }
    if (this.state === "walk") {
      const adv = this.stepTravel();
      if (this.dir * (cmd.goal - this.x) < Math.max(adv, 1) * 0.5) { this.next(); return "stop"; }   // stop on a frame boundary, never overshoot
      const hit = this.world.bodyAhead?.(this, adv);
      if (hit) { this.emit("bump", { other: hit.body }); hit.body.emit("bumped", { other: this }); this.queue = []; this.next(); return "stop"; }
      this.x += this.dir * adv; this.k = (this.k + 1) % n; this.enterFrame(); this.updatePins(); return;
    }
    if (this.state === "climb") {
      this.k++;
      const p = cmd.path[Math.min(this.k, n - 1)];
      this.x = cmd.start.x + (cmd.dir ?? 1) * p[0] * clip.scale; this.y = cmd.start.y + p[1] * clip.scale;
      if (this.k >= n) { this.k = n - 1; this.surface = cmd.type === "climb_up" ? cmd.platform : (cmd.to ?? "floor"); this.y = this.world.surfaceY(this.surface); this.next(); return "stop"; }
      this.enterFrame(); return;
    }
    if (this.state === "ladder") {
      const L = clip.ladder, l = this.world.ladder(cmd.ladder);
      this.y -= (L.rise_px[this.k] ?? L.rise_px_per_cycle / n) * clip.scale;
      this.k = (this.k + 1) % n; cmd.done++;
      if (cmd.done >= cmd.frames) {
        this.y = l.top; this.surface = l.toSurface ?? this.surface;
        this.emit("ladder_off", { ladder: l.id, note: "get-off is a cut: no get-off drawings" }); this.next(); return "stop";
      }
      this.enterFrame(); this.rungError = this.measureRungs(l); return;
    }
    if (this.state === "jump") {
      this.k++;
      const J = clip.jump, u = Math.max(0, Math.min(1, (this.k - J.takeoff_after) / (J.land_at - J.takeoff_after)));
      this.x = cmd.start.x + (cmd.x - cmd.start.x) * u;
      this.y = cmd.start.y + (cmd.landY - cmd.start.y) * u - J.arc_height_px * clip.scale * Math.sin(Math.PI * u);
      if (this.k >= n) { this.k = n - 1; this.surface = cmd.surface; this.y = cmd.landY; this.next(); return "stop"; }
      this.enterFrame(); return;
    }
    if (this.state === "pose") {
      if (cmd.i + 1 >= cmd.frames.length) { cmd.held = true; return "stop"; }
      this.k = cmd.frames[++cmd.i]; this.enterFrame(); if (cmd.i + 1 >= cmd.frames.length) cmd.held = true; return;
    }
    if (this.state === "play") {
      if (this.k + 1 >= n) { if (--cmd.left <= 0) { this.next(); return "stop"; } this.k = 0; this.enterFrame(); return; }
      this.k++; this.enterFrame();
    }
  }

  // --- drawing (canvas 2D)
  draw(ctx) {
    const clip = this.clip, f = clip.frames[this.k], s = clip.scale, [rx, ry, rw, rh] = f.rect;
    if (!clip.img) return;
    ctx.save(); ctx.translate(this.x, this.y); ctx.scale(this.dir * s, s);
    ctx.drawImage(clip.img, rx, ry, rw, rh, f.offset[0] - clip.anchor[0], f.offset[1] - clip.anchor[1], rw, rh);
    ctx.restore();
  }

  /** Debug overlay: contacts (green planted, orange free), red pins where planted contacts landed. */
  drawDebug(ctx) {
    for (const c of Object.values(this.clip.frames[this.k].contacts || {})) {
      const w = this.toWorld(c);
      ctx.beginPath(); ctx.arc(w.x, w.y, 3.5, 0, 7);
      if (c.state === "planted") { ctx.fillStyle = "#1baf7a"; ctx.fill(); } else { ctx.strokeStyle = "#eb6834"; ctx.lineWidth = 1.5; ctx.stroke(); }
    }
    if (this.state === "walk") for (const p of Object.values(this.pins)) { ctx.fillStyle = "#c81e28"; ctx.fillRect(p.x - 2, p.y - 10, 4, 14); }
    if (this.state === "walk" && this.overrideSliding) {   // a settings travel override (not contact-derived) makes the feet slide
      ctx.fillStyle = "#c81e28"; ctx.font = "bold 12px system-ui";
      ctx.fillText(`travel override: feet slide ${this.drift.toFixed(0)} px`, this.x - 70, this.y + 16);
    }
  }
}

/**
 * Drive characters with requestAnimationFrame at a fixed timestep (default 1/240 s) so 30, 60 and 144 Hz displays give the
 * same positions; pauses while the tab is hidden (no catch-up jump on return). `draw(frameDt)` runs once per display frame.
 * Returns a stop function; `run.paused` tells whether it is paused.
 */
export function run(characters, draw, { stepMs = 1000 / 240 } = {}) {
  const step = makeStepper(dt => { for (const c of characters) c.update(dt); }, stepMs);
  let last = performance.now(), on = true;
  const doc = globalThis.document;
  const vis = () => { run.paused = !!doc?.hidden; last = performance.now(); };
  doc?.addEventListener?.("visibilitychange", vis); vis();
  const loop = now => {
    if (!on) return;
    const dt = now - last; last = now;
    if (!run.paused) { step(dt); draw?.(Math.min(100, dt)); }
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
  return () => { on = false; doc?.removeEventListener?.("visibilitychange", vis); };
}
