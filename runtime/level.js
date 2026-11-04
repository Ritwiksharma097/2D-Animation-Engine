// Levels, navigation and camera for the animation runtime. Vanilla ES module, no DOM. Format: FORMAT.md "Levels".
import { World, adaptClimb } from "./anim.js";

const DEF_RULES = { jump_max_gap: 140, jump_max_rise: 12, jump_edge_inset: 30, cost_climb: 300, cost_jump: 150, cost_ladder: 400 };

/**
 * Compile a level (game px) into walk regions and props for a World.
 * A ledge stands on a floor and splits it: the floor left of the ledge ends in a "face" (the ledge front), the floor
 * right of it starts with a face (the ledge back). Floor ends and gaps are "edge"s. Floating platforms are surfaces too.
 */
export function compileLevel(level) {
  const rules = { ...DEF_RULES, ...(level.rules || {}) };
  const regions = [], platforms = [], ladders = [];
  for (const f of level.floors) {
    const ls = (level.ledges || []).filter(l => l.on === f.id).sort((a, b) => a.x0 - b.x0);
    let x = f.x0, left = "edge", k = 0, prev = null;
    for (const l of ls) {
      const r = { id: `${f.id}#${k++}`, floor: f.id, x0: x, x1: l.x0, y: f.y, left, right: "face" };
      regions.push(r);
      if (prev) prev.back = r.id;          // the region after a ledge is that ledge's back side
      prev = { id: l.id, kind: "ledge", x0: l.x0, x1: l.x1, top: l.top, base: f.y, front: r.id };
      platforms.push(prev);
      x = l.x1; left = "face";
    }
    const last = { id: `${f.id}#${k}`, floor: f.id, x0: x, x1: f.x1, y: f.y, left, right: "edge" };
    regions.push(last);
    if (prev) prev.back = last.id;
  }
  for (const p of level.platforms || []) platforms.push({ id: p.id, kind: "platform", x0: p.x0, x1: p.x1, top: p.top, base: null });
  const regionAt = (floorId, x) => regions.find(r => r.floor === floorId && r.x0 <= x && x <= r.x1);
  for (const l of level.ladders || []) {
    const from = level.floors.some(f => f.id === l.from) ? regionAt(l.from, l.x)?.id : l.from;
    const to = platforms.find(p => p.id === l.to) ?? regions.find(r => r.id === l.to);
    ladders.push({ id: l.id, x: l.x, from, toSurface: to.id, top: to.top ?? to.y, rungSpacing: l.rung_spacing ?? 32 });
  }
  const surfaces = [...regions.map(r => ({ ...r, kind: "floor" })), ...platforms.map(p => ({ ...p, y: p.top, left: "edge", right: "edge" }))];
  return { level, rules, regions, platforms, ladders, surfaces, hotspots: level.hotspots || [] };
}

export function worldFromLevel(compiled) {
  return new World({ floors: compiled.regions, platforms: compiled.platforms, ladders: compiled.ladders });
}

/** The surface a click at (x, y) means: the nearest surface at or below the click whose span contains x. */
export function surfaceAt(compiled, x, y) {
  const c = compiled.surfaces.filter(s => s.x0 <= x && x <= s.x1);
  const below = c.filter(s => s.y >= y - 20).sort((a, b) => a.y - b.y);
  return below[0] ?? c.sort((a, b) => Math.abs(a.y - y) - Math.abs(b.y - y))[0] ?? null;
}

/**
 * Transitions between surfaces, each with ok / reason judged from the character's own drawings:
 * climbs via the ledge-height adapter (both faces), jumps by gap and rise limits, ladders only with a ladder clip that has
 * rung data (and only upward: there is no ladder-down drawing).
 */
export function navGraph(compiled, character) {
  const { rules } = compiled, edges = [];
  const has = role => { try { return character.c(role); } catch { return null; } };
  const upC = has("climb_up"), downC = has("climb_down"), jumpC = has("jump"), ladC = has("ladder");
  for (const p of compiled.platforms.filter(p => p.kind === "ledge")) {
    const height = p.base - p.top;
    for (const side of ["front", "back"]) {
      const region = side === "front" ? p.front : p.back;
      if (!region) continue;
      const au = upC ? adaptClimb(upC, height) : { ok: false, reason: "no climb_up drawings" };
      const ad = downC ? adaptClimb(downC, height) : { ok: false, reason: "no climb_down drawings" };
      edges.push({ type: "climb_up", from: region, to: p.id, platform: p.id, side, ok: au.ok, marginal: !!au.marginal, reason: au.reason,
                   fromX: au.ok ? character.climbStartX("climb_up", p.id, side) : (side === "front" ? p.x0 : p.x1),
                   toX: au.ok ? character.climbEndX("climb_up", p.id, side) : (p.x0 + p.x1) / 2, cost: rules.cost_climb });
      edges.push({ type: "climb_down", from: p.id, to: region, platform: p.id, side, ok: ad.ok, marginal: !!ad.marginal, reason: ad.reason,
                   fromX: ad.ok ? character.climbStartX("climb_down", p.id, side) : (p.x0 + p.x1) / 2,
                   toX: ad.ok ? character.climbEndX("climb_down", p.id, side) : (side === "front" ? p.x0 : p.x1), cost: rules.cost_climb });
    }
  }
  const S = compiled.surfaces;
  for (const a of S) for (const b of S) {
    if (a === b || a.right !== "edge" || b.left !== "edge") continue;
    const gap = b.x0 - a.x1, rise = a.y - b.y;
    if (gap <= 0 || gap > rules.jump_max_gap * 2) continue;      // too far even to show as a red transition
    let ok = !!jumpC?.jump, reason = ok ? null : "no jump drawings with timing";
    if (ok && gap > rules.jump_max_gap) { ok = false; reason = `gap ${gap.toFixed(0)} px > jump_max_gap ${rules.jump_max_gap}`; }
    if (ok && Math.abs(rise) > rules.jump_max_rise) { ok = false; reason = `height change ${rise.toFixed(0)} px > jump_max_rise ${rules.jump_max_rise}`; }
    const ins = rules.jump_edge_inset;
    edges.push({ type: "jump", from: a.id, to: b.id, ok, reason, fromX: a.x1 - ins, toX: b.x0 + ins, cost: rules.cost_jump });
    edges.push({ type: "jump", from: b.id, to: a.id, ok, reason, fromX: b.x0 + ins, toX: a.x1 - ins, cost: rules.cost_jump });
  }
  for (const l of compiled.ladders) {
    const ok = !!ladC?.ladder;
    edges.push({ type: "ladder", from: l.from, to: l.toSurface, ladder: l.id, ok, reason: ok ? null : "no ladder drawings with rung data for this character",
                 fromX: l.x, toX: l.x, cost: compiled.rules.cost_ladder });
    edges.push({ type: "ladder_down", from: l.toSurface, to: l.from, ladder: l.id, ok: false, reason: "no ladder-down drawings", fromX: l.x, toX: l.x, cost: compiled.rules.cost_ladder });
  }
  return edges;
}

/**
 * Shortest route from {surface, x} to {surface, x} using only ok transitions. Returns {ok, steps, cost} or
 * {ok:false, reason, blocked} listing the refused transitions that would have led there.
 */
export function planRoute(compiled, edges, from, to) {
  const usable = edges.filter(e => e.ok);
  // nodes: start, goal, and both ends of every usable transition
  const nodes = [{ s: from.surface, x: from.x, id: "start" }, { s: to.surface, x: to.x, id: "goal" }];
  usable.forEach((e, i) => { nodes.push({ s: e.from, x: e.fromX, id: `a${i}`, e: i }); nodes.push({ s: e.to, x: e.toX, id: `b${i}`, e: i }); });
  const dist = new Map(nodes.map(n => [n.id, Infinity])), prev = new Map(), done = new Set();
  dist.set("start", 0);
  while (true) {
    let u = null; for (const n of nodes) if (!done.has(n.id) && (u === null || dist.get(n.id) < dist.get(u.id))) u = n;
    if (!u || dist.get(u.id) === Infinity) break;
    if (u.id === "goal") break;
    done.add(u.id);
    const relax = (v, w, via) => { const d = dist.get(u.id) + w; if (d < dist.get(v.id)) { dist.set(v.id, d); prev.set(v.id, { u, via }); } };
    for (const v of nodes) if (v !== u && v.s === u.s && !v.id.startsWith("b")) relax(v, Math.abs(v.x - u.x), "walk");   // walk on the same surface
    if (u.id.startsWith("a")) relax(nodes.find(n => n.id === `b${u.e}`), usable[u.e].cost, usable[u.e]);          // take the transition
  }
  if (dist.get("goal") === Infinity) {
    const blocked = edges.filter(e => !e.ok && (e.to === to.surface || e.from === from.surface));
    return { ok: false, reason: blocked.length ? blocked.map(e => `${e.type} ${e.from}->${e.to}: ${e.reason}`).join("; ") : "no route", blocked };
  }
  const chain = []; let id = "goal";
  while (id !== "start") { const p = prev.get(id); chain.unshift({ node: nodes.find(n => n.id === id), via: p.via }); id = p.u.id; }
  const steps = [];
  for (const { node, via } of chain) {
    if (via === "walk") { if (steps.length && steps[steps.length - 1].type === "walk") steps.pop(); steps.push({ type: "walk", surface: node.s, x: node.x }); }
    else steps.push({ ...via });
  }
  return { ok: true, steps, cost: dist.get("goal") };
}

/** Queue a planned route on a runtime Character. */
export function queueRoute(character, steps) {
  for (const s of steps) {
    if (s.type === "walk") character.walkTo(s.x);
    else if (s.type === "climb_up") character.climbUp(s.platform, { side: s.side });
    else if (s.type === "climb_down") character.climbDown(s.platform, { side: s.side, to: s.to });
    else if (s.type === "jump") character.jumpTo(s.toX, s.to);
    else if (s.type === "ladder") character.queue.push({ type: "ladder", ladder: s.ladder });
  }
  return character;
}

/** Route a character to a clicked point. */
export function goTo(compiled, edges, character, x, y) {
  const target = surfaceAt(compiled, x, y);
  if (!target) return { ok: false, reason: "nothing to stand on there" };
  const route = planRoute(compiled, edges, { surface: character.surface, x: character.x }, { surface: target.id, x });
  if (route.ok) queueRoute(character, route.steps);
  return { ...route, target: target.id };
}

/** A side-scrolling camera: keeps the target inside a dead zone, eases toward it, clamps to the level. */
export class Camera {
  constructor({ viewW, levelW, deadZone = 0.3, ease = 0.12 }) { Object.assign(this, { viewW, levelW, deadZone, ease }); this.x = 0; }
  update(targetX, dtMs = 16.7) {
    const lo = this.x + this.viewW * this.deadZone, hi = this.x + this.viewW * (1 - this.deadZone);
    let want = this.x;
    if (targetX < lo) want = targetX - this.viewW * this.deadZone;
    else if (targetX > hi) want = targetX - this.viewW * (1 - this.deadZone);
    const k = 1 - Math.pow(1 - this.ease, dtMs / 16.7);   // frame-rate independent easing
    this.x += (want - this.x) * k;
    this.x = Math.max(0, Math.min(this.levelW - this.viewW, this.x));
    return this.x;
  }
  snap(targetX) { this.x = Math.max(0, Math.min(this.levelW - this.viewW, targetX - this.viewW / 2)); return this.x; }
}
