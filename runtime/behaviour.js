// Interactions and behaviour on top of the runtime. Decisions are pure functions of (state, perception, dt, config)
// so they can be unit-tested without animation; the classes wire them to runtime Characters. Config is plain JSON.

// ------------------------------------------------------------------ geometry

/** Does the segment a->b cross the rectangle r {x0, x1, y0, y1}? (Liang-Barsky) */
export function segmentHitsRect(a, b, r) {
  let t0 = 0, t1 = 1;
  const dx = b.x - a.x, dy = b.y - a.y;
  for (const [p, q] of [[-dx, a.x - r.x0], [dx, r.x1 - a.x], [-dy, a.y - r.y0], [dy, r.y1 - a.y]]) {
    if (p === 0) { if (q < 0) return false; continue; }
    const t = q / p;
    if (p < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; }
  }
  return true;
}

/**
 * Can an eye at `eye`, facing `dir` (+1 right / -1 left), see `target`? Within `range`, inside a cone of `halfAngleDeg`
 * around the facing, and with no `solids` ({x0,x1,y0,y1}) on the line of sight. Returns {seen, reason, distance}.
 */
export function canSee(eye, dir, target, { range, halfAngleDeg }, solids = []) {
  const dx = target.x - eye.x, dy = target.y - eye.y, d = Math.hypot(dx, dy);
  if (d > range) return { seen: false, reason: "out of range", distance: d };
  if (dx * dir <= 0) return { seen: false, reason: "behind", distance: d };
  const ang = Math.atan2(Math.abs(dy), Math.abs(dx)) * 180 / Math.PI;
  if (ang > halfAngleDeg) return { seen: false, reason: "outside the cone", distance: d };
  for (const s of solids) if (segmentHitsRect(eye, target, s)) return { seen: false, reason: "blocked", distance: d, by: s.id };
  return { seen: true, reason: "seen", distance: d };
}

/** Solids that block sight in a compiled level: ledge blocks and (thin) platforms. */
export function sightBlockers(compiled) {
  return [...compiled.platforms.map(p => ({ id: p.id, x0: p.x0, x1: p.x1, y0: p.top, y1: p.kind === "ledge" ? p.base : p.top + 14 }))];
}

// ------------------------------------------------------------------ guard decisions (pure)

export const GUARD_DEFAULTS = {
  patrol: [100, 900], wait_at_ends_ms: 1500,
  vision: { range: 320, halfAngleDeg: 28, eye_height: 150, target_height: 90 },
  suspicion: { rise_per_s: 0.9, decay_per_s: 0.4, suspicious_at: 0.3, caught_at: 1.0, look_ms: 2500 },
  notice: { radius: 90, still_radius: 50, rise_per_s: 0.6, bump_to: 0.5 },
  food: { notice_range: 600, eat_loops: 1 },
};

/**
 * The caught rule, in one place: the suspicion meter fills while the guard sees Ren (`suspicion.rise_per_s`) or hears him
 * within `notice.radius` (`notice.rise_per_s`); a bump sets it to at least `notice.bump_to`. It drains at `decay_per_s`
 * otherwise. When it reaches `caught_at`, Ren is caught, wherever he is (the guard doesn't have to reach him).
 * In plain sight from an empty meter that takes caught_at / rise_per_s seconds.
 */
export function suspicionStep(value, p, dt, S, N) {
  const secs = dt / 1000;
  let v = value ?? 0;
  if (p.sees) v += S.rise_per_s * secs; else if (p.heard) v += N.rise_per_s * secs; else v -= S.decay_per_s * secs;
  if (p.bumped) v = Math.max(v, N.bump_to);
  return Math.max(0, Math.min(S.caught_at, v));
}

/** Seconds of plain sight that fill the meter from `value`. */
export const secondsToCatch = (cfg = GUARD_DEFAULTS, value = 0) => (cfg.suspicion.caught_at - value) / cfg.suspicion.rise_per_s;

/**
 * One decision step. state: {mode, suspicion, timer}. perception: {sees, heard, bumped, renX, foodX, guardX, guardDir, lovestruck, ...}.
 * Returns {state, actions}; actions are commands for the body: {do: "patrol"|"walk"|"face"|"play"|"look"|"catch", ...}.
 * Modes: patrol -> suspicious (looks around; faces a noise) -> caught when the meter is full;
 * any -> distracted (food) -> eating -> patrol; lovestruck (hook).
 */
export function decideGuard(state, p, dt, cfg = GUARD_DEFAULTS) {
  const s = { ...state }, out = [], S = { ...GUARD_DEFAULTS.suspicion, ...cfg.suspicion }, N = { ...GUARD_DEFAULTS.notice, ...(cfg.notice || {}) };
  s.timer = (s.timer ?? 0) + dt;
  const go = (mode, ...acts) => { s.mode = mode; s.timer = 0; out.push(...acts); };
  if (s.mode === "caught") return { state: s, actions: out };
  if (p.lovestruck && s.mode !== "lovestruck") { go("lovestruck", { do: "play", role: "love" }); return { state: s, actions: out }; }
  if (s.mode === "lovestruck") { if (!p.lovestruck) go("patrol", { do: "patrol" }); return { state: s, actions: out }; }
  s.suspicion = suspicionStep(s.suspicion, p, dt, S, N);
  if (s.suspicion >= S.caught_at) { go("caught", { do: "catch" }); return { state: s, actions: out }; }
  const behindHim = p.guardDir !== undefined && (p.renX - p.guardX) * p.guardDir < 0;
  if ((p.heard || p.bumped) && !p.sees && behindHim && s.mode !== "eating") {   // a noise behind him: he turns to look
    out.push({ do: "face", dir: -p.guardDir });
    if (s.mode !== "suspicious") { s.mode = "suspicious"; s.timer = 0; }
    return { state: s, actions: out };
  }
  if (p.foodX !== null && p.foodX !== undefined && Math.abs(p.foodX - p.guardX) <= cfg.food.notice_range && s.mode !== "eating"
      && s.suspicion < S.suspicious_at) {
    if (s.mode !== "distracted") go("distracted", { do: "walk", x: p.foodX, toFood: true });
    else if (p.atFood) go("eating", { do: "play", role: "eat" });
    return { state: s, actions: out };
  }
  if (s.mode === "eating") { if (p.doneEating) go("patrol", { do: "patrol" }); return { state: s, actions: out }; }
  if (s.suspicion >= S.suspicious_at && s.mode !== "suspicious") { go("suspicious", { do: "look" }); return { state: s, actions: out }; }
  if (s.mode === "suspicious") {
    if (s.suspicion < 0.05 && s.timer > S.look_ms) go("patrol", { do: "play", role: "angry" }, { do: "patrol" });
    return { state: s, actions: out };
  }
  if (!s.mode || s.mode === "distracted") go("patrol", { do: "patrol" });
  return { state: s, actions: out };
}

// ------------------------------------------------------------------ Ren's idle hint (pure)

/** After `after_ms` standing idle, return {do:"play", role:"look_around"} once and emit a hint (a hook for "looks at the player"). */
export function decideIdleHint(state, idle, dt, cfg = { after_ms: 6000 }) {
  const s = { idleMs: idle ? (state.idleMs ?? 0) + dt : 0, fired: idle ? state.fired : false };
  if (idle && !s.fired && s.idleMs >= cfg.after_ms) { s.fired = true; return { state: s, actions: [{ do: "play", role: "look_around", hint: true }] }; }
  return { state: s, actions: [] };
}

// ------------------------------------------------------------------ inventory + hotspots

export class Inventory {
  constructor() { this.items = []; }
  add(item) { this.items.push(item); return this; }
  has(id) { return this.items.some(i => i.id === id); }
  remove(id) { const k = this.items.findIndex(i => i.id === id); return k >= 0 ? this.items.splice(k, 1)[0] : null; }
}

/** How far ahead of a character's anchor (game px) a clip's named event point lies, e.g. where the hand meets the ground. */
export function eventReach(clip, name) {
  const e = clip.events?.[name];
  return e?.point ? (e.point[0] - clip.anchor[0]) * clip.scale : 0;
}

/**
 * Hotspot actions, data-driven. `defs` maps a hotspot `use` to {role, event} (e.g. {"interact": {role: "interact",
 * event: "pickup"}}). take(): walk so the event point lands on the item, play the role, take the item at the event.
 */
export class Interactions {
  constructor({ hotspots, inventory = new Inventory(), defs = { interact: { role: "interact", event: "pickup" } } }) {
    this.hotspots = hotspots; this.inventory = inventory; this.defs = defs; this.handlers = {};
  }
  on(evt, fn) { (this.handlers[evt] ??= []).push(fn); return this; }
  emit(evt, data) { for (const fn of this.handlers[evt] || []) fn(data); }
  near(character, maxDx = 400) { return this.hotspots.filter(h => h.on === character.surface && Math.abs(h.x - character.x) <= maxDx); }
  take(character, hotspotId) {
    const h = this.hotspots.find(h => h.id === hotspotId);
    if (!h) return false;
    const def = this.defs[h.use] ?? this.defs.interact, clip = character.c(def.role);
    const dir = h.x >= character.x ? 1 : -1, reach = eventReach(clip, def.event);
    character.walkTo(h.x - dir * reach);
    if (character.dir !== dir) character.turn(dir);
    character.play(def.role);
    const onEvent = () => {
      character.handlers[def.event] = (character.handlers[def.event] || []).filter(f => f !== onEvent);
      this.hotspots = this.hotspots.filter(x => x !== h);
      this.inventory.add({ id: h.item ?? h.id, from: h.id });
      this.emit("taken", { item: h.item ?? h.id, hotspot: h, character });
    };
    character.on(def.event, onEvent);
    return true;
  }
  drop(character, itemId, { x = character.x + character.dir * 30, surface = character.surface } = {}) {
    const it = this.inventory.remove(itemId);
    if (!it) return null;
    const h = { id: `${itemId}_${Date.now() % 100000}`, x, on: surface, kind: "item", item: itemId, use: "interact" };
    this.hotspots.push(h); this.emit("dropped", { item: itemId, hotspot: h, character });
    return h;
  }
  /** Throw an item to x on a surface; lands after flightMs (a projectile the page can draw from `thrown`). */
  throwItem(character, itemId, x, surface, { flightMs = 600 } = {}) {
    const it = this.inventory.remove(itemId);
    if (!it) return null;
    const t = { item: itemId, from: { x: character.x, y: character.y - 60 }, to: { x, surface }, t: 0, flightMs };
    (this.thrown ??= []).push(t); this.emit("thrown", t);
    return t;
  }
  update(dt) {
    for (const t of this.thrown ?? []) {
      t.t += dt;
      if (t.t >= t.flightMs && !t.landed) {
        t.landed = true;
        const h = { id: `${t.item}_${Date.now() % 100000}`, x: t.to.x, on: t.to.surface, kind: "item", item: t.item, use: "interact" };
        this.hotspots.push(h); this.emit("landed", { item: t.item, hotspot: h });
      }
    }
    this.thrown = (this.thrown ?? []).filter(t => !t.landed);
  }
}

// ------------------------------------------------------------------ guard brain wired to a runtime Character

export class GuardBrain {
  constructor({ guard, config = {}, world, solids = [] }) {
    this.g = guard; this.world = world; this.solids = solids;
    this.cfg = { ...GUARD_DEFAULTS, ...config, vision: { ...GUARD_DEFAULTS.vision, ...(config.vision || {}) },
      suspicion: { ...GUARD_DEFAULTS.suspicion, ...(config.suspicion || {}) }, notice: { ...GUARD_DEFAULTS.notice, ...(config.notice || {}) } };
    this.bumped = false;
    guard.on("bump", () => { this.bumped = true; }); guard.on("bumped", () => { this.bumped = true; });
    this.state = { mode: null, suspicion: 0 }; this.handlers = {}; this.last = { seen: false };
    this.end = 1; this.food = null; this.lovestruck = false;
    guard.on("done", e => { if (e.command.type === "play" && e.command.role === "eat") { this.doneEating = true; this.food = null; this.emit("ate", {}); } });
  }
  on(evt, fn) { (this.handlers[evt] ??= []).push(fn); return this; }
  emit(evt, data) { for (const fn of this.handlers[evt] || []) fn(data); }
  eye() { return { x: this.g.x, y: this.g.y - this.cfg.vision.eye_height }; }
  look(ren) {
    if (!ren || ren.hidden) return { seen: false, reason: "no target" };
    if (ren.hidingIn) {   // in a hiding spot (runtime/scene.js): seen only within its reveal_radius
      const d = Math.abs(ren.x - this.g.x);
      if (d > ren.hidingIn.reveal_radius) return { seen: false, reason: `hidden (${ren.hidingIn.id})`, distance: d };
    }
    const target = { x: ren.x, y: ren.y - this.cfg.vision.target_height };
    const r = canSee(this.eye(), this.g.dir, target, this.cfg.vision, this.solids);
    // close in front (within notice.radius, same height) is seen even below the cone, unless a prop is in the way
    if (r.reason === "outside the cone" && Math.abs(ren.y - this.g.y) < 60 && Math.abs(ren.x - this.g.x) <= this.cfg.notice.radius) {
      const near = canSee(this.eye(), this.g.dir, target, { range: Infinity, halfAngleDeg: 90 }, this.solids);
      if (near.seen) return { seen: true, reason: "close in front", distance: r.distance };
    }
    return r;
  }
  /**
   * Hearing: Ren moving within notice.radius, or standing within notice.still_radius (game px, feet to feet, about the same
   * height), even when he isn't seen. `ren.silent` (e.g. keeping still in a hiding spot) is never heard.
   */
  hear(ren) {
    if (!ren || ren.hidden || ren.silent || Math.abs(ren.y - this.g.y) >= 60) return false;
    const d = Math.abs(ren.x - this.g.x), moving = ren.state !== "idle" && ren.state !== "wait";
    return d <= (moving ? this.cfg.notice.radius : this.cfg.notice.still_radius);
  }
  update(dt, ren) {
    const g = this.g, sight = this.look(ren), heard = !sight.seen && this.hear(ren), bumped = this.bumped;
    this.bumped = false;
    this.last = { ...sight, heard, bumped };
    const atFood = this.food && Math.abs(g.x - this.foodApproach) < 6 && !g.busy;
    const { state, actions } = decideGuard(this.state, { sees: sight.seen, heard, bumped, renX: ren?.x ?? 0, guardX: g.x, guardDir: g.dir, foodX: this.food?.x ?? null, guardIdle: !g.busy,
      atFood, doneEating: this.doneEating, lovestruck: this.lovestruck }, dt, this.cfg);
    if (state.mode !== this.state.mode) this.emit("mode", { from: this.state.mode, to: state.mode });
    this.state = state;
    for (const a of actions) this.act(a, ren);
    if (state.mode === "patrol" && !g.busy) {   // keep patrolling between the ends, with a pause at each
      const [x0, x1] = this.cfg.patrol; this.end = Math.abs(g.x - x1) < Math.abs(g.x - x0) ? 0 : 1;
      g.wait(this.cfg.wait_at_ends_ms).walkTo(this.end ? x1 : x0);
    }
    if (state.mode === "suspicious" && !g.busy && !sight.seen && !heard) g.wait(500).turn(-g.dir);   // no look-around drawing: alternate facing; keeps staring while he sees Ren
  }
  act(a, ren) {
    const g = this.g;
    if (a.do === "patrol") { g.clear(); if (g.state === "walk") g.next(); }
    else if (a.do === "walk") {
      if (a.toFood) { const reach = this.foodReach ?? 0, dir = a.x >= g.x ? 1 : -1; this.foodApproach = a.x - dir * reach; g.clear(); if (g.state !== "idle") g.next(); g.walkTo(this.foodApproach); if (g.dir !== dir) g.turn(dir); }
      else { g.clear(); if (g.state === "walk" || g.state === "wait") g.next(); g.walkTo(a.x); }
    } else if (a.do === "play") {
      g.clear(); if (g.state !== "idle" && g.state !== "play") g.next();
      g.play(a.role, { loops: a.role === "eat" ? this.cfg.food.eat_loops ?? 1 : 1 }); if (a.role === "eat") this.doneEating = false;
    }
    else if (a.do === "face") { if (g.dir !== a.dir && g.state !== "turn") { g.clear(); if (g.state === "walk" || g.state === "wait") g.next(); g.turn(a.dir); } }
    else if (a.do === "look") { g.clear(); if (g.state === "walk") g.next(); this.emit("suspicious", {}); }
    else if (a.do === "catch") { g.clear(); if (g.state !== "idle") g.next(); g.play("angry"); this.emit("caught", { ren }); }
  }
  /** The page calls this when food appears (e.g. an item lands); the guard notices it if in range. */
  setFood(food, reach = 0) { this.food = food; this.foodReach = reach; this.doneEating = false; }
}
