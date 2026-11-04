// Simple cutscenes: a JSON timeline of steps run one after another, triggered by level start, hotspots or events, and
// skippable. DOM-free (Node-testable). Format: FORMAT.md "Sequences".
//
// Steps: {do: "walk", who, x} | {do: "play", who, role, loops} | {do: "face", who, dir | toward} | {do: "wait", ms}
//        {do: "emote", who, kind, ms, wait} | {do: "camera", x | who, ms} | {do: "fade", to: 0..1, ms}
//        {do: "flag", name, value} | {do: "sound", id}

const ease = u => u * u * (3 - 2 * u);

/**
 * Runs one sequence. ctx: {actors: {id: Character}, emotes, sounds, flags, view: {w}}. While running it owns the
 * camera (`cameraX`, null = not overriding) and an overlay alpha (`overlay`) the page draws.
 */
export class Sequence {
  constructor(def, ctx) {
    this.def = def; this.ctx = ctx; this.i = -1; this.t = 0; this.done = false; this.skipped = false;
    this.cameraX = null; this.overlay = ctx.overlay ?? 0; this.cur = null;
    this.next();
  }
  actor(who) { const a = this.ctx.actors[who]; if (!a) throw new Error(`sequence ${this.def.id}: no actor "${who}"`); return a; }
  stop(a) { a.clear(); if (a.state !== "idle") a.next(); }
  next() {
    this.i++; this.t = 0;
    if (this.i >= this.def.steps.length) { this.done = true; this.cur = null; this.cameraX = null; return; }
    const s = this.cur = this.def.steps[this.i];
    if (s.do === "walk") { const a = this.actor(s.who); this.stop(a); a.walkTo(s.x); }
    else if (s.do === "play") { const a = this.actor(s.who); this.stop(a); a.play(s.role, { loops: s.loops ?? 1 }); }
    else if (s.do === "face") { const a = this.actor(s.who); const dir = this.faceDir(s, a); if (dir !== a.dir) { this.stop(a); a.turn(dir); } }
    else if (s.do === "emote") this.ctx.emotes?.show(s.who, s.kind, s.ms ?? 1200);
    else if (s.do === "camera") { this.camFrom = this.cameraX ?? this.ctx.cameraX ?? 0; this.camTo = this.camTarget(s); }
    else if (s.do === "fade") this.fadeFrom = this.overlay;
    else if (s.do === "flag") this.ctx.flags[s.name] = s.value ?? true;
    else if (s.do === "sound") this.ctx.sounds?.play(s.id);
    else if (s.do !== "wait") throw new Error(`sequence ${this.def.id}: unknown step "${s.do}"`);
    if (this.finished(0)) this.next();
  }
  faceDir(s, a) {
    if (s.dir) return s.dir;
    const x = typeof s.toward === "number" ? s.toward : this.actor(s.toward).x;
    return x >= a.x ? 1 : -1;
  }
  camTarget(s) { return (s.x ?? this.actor(s.who).x) - (this.ctx.view?.w ?? 0) / 2; }
  /** Is the current step complete after `t` ms? */
  finished(t) {
    const s = this.cur;
    if (s.do === "walk" || s.do === "play" || s.do === "face") return !this.actor(s.who).busy;
    if (s.do === "wait") return t >= s.ms;
    if (s.do === "emote") return !s.wait || t >= (s.ms ?? 1200);
    if (s.do === "camera" || s.do === "fade") return t >= (s.ms ?? 0);
    return true;
  }
  update(dt) {
    if (this.done) return;
    this.t += dt;
    const s = this.cur, u = s.ms ? Math.min(1, this.t / s.ms) : 1;
    if (s.do === "camera") this.cameraX = this.camFrom + (this.camTo - this.camFrom) * ease(u);
    if (s.do === "fade") this.overlay = this.fadeFrom + (s.to - this.fadeFrom) * u;
    let guard = 0;
    while (!this.done && this.finished(this.t) && guard++ < 100) this.next();
  }
  /** Jump to the end: every remaining step's end state is applied at once (walks teleport, plays stop, flags set). */
  skip() {
    if (this.done) return;
    this.skipped = true;
    for (let k = this.i; k < this.def.steps.length; k++) {
      const s = this.def.steps[k];
      if (s.do === "walk") { const a = this.actor(s.who); this.stop(a); a.x = s.x; }
      else if (s.do === "play") this.stop(this.actor(s.who));
      else if (s.do === "face") { const a = this.actor(s.who); this.stop(a); a.dir = this.faceDir(s, a); }
      else if (s.do === "fade") this.overlay = s.to;
      else if (s.do === "flag") this.ctx.flags[s.name] = s.value ?? true;
    }
    this.ctx.emotes?.clear();
    this.i = this.def.steps.length; this.done = true; this.cur = null; this.cameraX = null;
  }
}

/**
 * Sequences of a level, with triggers: {on: "level_start"} | {on: "hotspot", id} | {on: "event", name} and `once`
 * (default true). One runs at a time; `running` tells the page to ignore player input. `flags` persist across them.
 */
export class Sequences {
  constructor(defs = [], ctx) { this.defs = defs; this.ctx = { flags: {}, ...ctx }; this.flags = this.ctx.flags; this.seen = ctx?.seen ?? new Set(); this.current = null; this.log = []; }
  get running() { return !!this.current && !this.current.done; }
  matches(def, trig) {
    const t = def.trigger || {};
    if (t.on !== trig.on) return false;
    if (t.on === "hotspot" && t.id !== trig.id) return false;
    if (t.on === "event" && t.name !== trig.name) return false;
    if (def.requires && !Object.entries(def.requires).every(([k, v]) => (this.flags[k] ?? false) === v)) return false;
    return !((def.once ?? true) && this.seen.has(def.id));
  }
  /** Start the first sequence matching a trigger; returns it, or null. */
  fire(trig) {
    if (this.running) return null;
    const def = this.defs.find(d => this.matches(d, trig));
    if (!def) return null;
    this.seen.add(def.id); this.log.push(def.id);
    this.current = new Sequence(def, { ...this.ctx, flags: this.flags, overlay: this.current?.overlay ?? 0 });
    return this.current;
  }
  update(dt) { if (this.current && !this.current.done) this.current.update(dt); }
  /** Skip the running sequence if it is skippable (default true). */
  skip() { if (this.running && (this.current.def.skippable ?? true)) { this.current.skip(); return true; } return false; }
  get cameraX() { return this.running ? this.current.cameraX : null; }
  get overlay() { return this.current?.overlay ?? 0; }
}
