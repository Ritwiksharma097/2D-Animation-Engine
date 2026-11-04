// Objects with state (doors, chests, levers, lamps) and simple puzzles as JSON rules. The condition and effect logic is
// pure (Node-testable); `ObjectBodies` turns closed doors into solids the runtime's characters stop at.
// Level keys (FORMAT.md "Objects and puzzles"): objects, puzzle (explicit rules).
//
// A puzzle state is plain data: {states: {objectId: "locked"|"closed"|"open"|"on"|"off"}, flags: {}, inventory: [ids],
// taken: [hotspot ids]}. Actions are {interact: objectId} or {use: itemId, on: objectId}.

export const OBJECT_DEFAULTS = {
  door:  { state: "closed", width: 24, height: 150 },
  chest: { state: "closed", width: 70, height: 50, contains: [] },
  lever: { state: "off", width: 16, height: 60 },
  lamp:  { state: "off", width: 20, height: 120 },
};

export function objectsFromLevel(level) {
  return (level.objects || []).map(o => ({ ...OBJECT_DEFAULTS[o.kind], ...o, contains: [...(o.contains ?? OBJECT_DEFAULTS[o.kind]?.contains ?? [])] }));
}

/** A fresh puzzle state for a level's objects. */
export function initialState(objects, { inventory = [], flags = {} } = {}) {
  return { states: Object.fromEntries(objects.map(o => [o.id, o.state])), flags: { ...flags }, inventory: [...inventory], taken: [] };
}

/**
 * Does a condition hold? cond: {flags: {name: value}, has: itemId | [ids], lacks: itemId, state: {objectId: state | [states]},
 * all: [cond], any: [cond], not: cond}. An empty or missing condition holds.
 */
export function check(cond, st) {
  if (!cond) return true;
  const list = v => (Array.isArray(v) ? v : [v]);
  if (cond.flags && !Object.entries(cond.flags).every(([k, v]) => (st.flags[k] ?? false) === v)) return false;
  if (cond.has !== undefined && !list(cond.has).every(i => st.inventory.includes(i))) return false;
  if (cond.lacks !== undefined && list(cond.lacks).some(i => st.inventory.includes(i))) return false;
  if (cond.state && !Object.entries(cond.state).every(([id, s]) => list(s).includes(st.states[id]))) return false;
  if (cond.all && !cond.all.every(c => check(c, st))) return false;
  if (cond.any && !cond.any.some(c => check(c, st))) return false;
  if (cond.not && check(cond.not, st)) return false;
  return true;
}

/**
 * Apply effects in order; returns the new state (inputs untouched) and the events they caused, for the page to show
 * (messages, sequences to run, emotes, sounds). Effects: {set: {objectId: state}}, {toggle: objectId} (on/off, open/closed),
 * {flag: {name: value}}, {give: itemId}, {take: itemId}, {message: text}, {sequence: id}, {emote: {who, kind}}, {sound: id}.
 */
export function apply(effects, st) {
  const s = { states: { ...st.states }, flags: { ...st.flags }, inventory: [...st.inventory], taken: [...(st.taken ?? [])] }, events = [];
  for (const e of effects || []) {
    if (e.set) for (const [id, v] of Object.entries(e.set)) { events.push({ type: "state", id, from: s.states[id], to: v }); s.states[id] = v; }
    if (e.toggle) { const v = s.states[e.toggle], to = { on: "off", off: "on", open: "closed", closed: "open" }[v] ?? v; events.push({ type: "state", id: e.toggle, from: v, to }); s.states[e.toggle] = to; }
    if (e.flag) Object.assign(s.flags, e.flag);
    if (e.give && !s.inventory.includes(e.give)) { s.inventory.push(e.give); events.push({ type: "give", item: e.give }); }
    if (e.take) { s.inventory = s.inventory.filter(i => i !== e.take); events.push({ type: "take", item: e.take }); }
    for (const k of ["message", "sequence", "emote", "sound"]) if (e[k] !== undefined) events.push({ type: k, value: e[k] });
  }
  return { state: s, events };
}

/**
 * The built-in behaviour of each object kind, as rules (explicit level rules come first and win):
 * - door: `locked_by` item unlocks it (to "closed", or "open" with `opens_when_unlocked`), `consume` removes the item;
 *   interacting toggles open/closed; a locked door says so.
 * - chest: interacting opens a closed chest and gives `contains` once; `locked_by` as for doors.
 * - lever / lamp: interacting toggles on/off; a lever's `controls` sets those objects ({id: [stateWhenOn, stateWhenOff]}).
 */
export function builtinRules(objects) {
  const R = [];
  for (const o of objects) {
    if (o.locked_by) {
      R.push({ id: `${o.id}:unlock`, when: { use: o.locked_by, on: o.id }, if: { state: { [o.id]: "locked" } },
               then: [{ set: { [o.id]: o.opens_when_unlocked ? "open" : "closed" } }, ...(o.consume ? [{ take: o.locked_by }] : []), { message: `unlocked the ${o.kind}` }, { sound: "unlock" }] });
      R.push({ id: `${o.id}:locked`, when: { interact: o.id }, if: { state: { [o.id]: "locked" } }, then: [{ message: `the ${o.kind} is locked` }, { sound: "locked" }] });
    }
    if (o.kind === "door") R.push({ id: `${o.id}:toggle`, when: { interact: o.id }, if: { state: { [o.id]: ["open", "closed"] } }, then: [{ toggle: o.id }, { sound: "door" }] });
    if (o.kind === "chest") R.push({ id: `${o.id}:open`, when: { interact: o.id }, if: { state: { [o.id]: "closed" } },
                                     then: [{ set: { [o.id]: "open" } }, ...o.contains.map(i => ({ give: i })), { message: o.contains.length ? `found: ${o.contains.join(", ")}` : "empty" }, { sound: "chest" }] });
    if (o.kind === "lever" || o.kind === "lamp") {
      const controls = Object.entries(o.controls || {});
      R.push({ id: `${o.id}:on`, when: { interact: o.id }, if: { state: { [o.id]: "off" } }, then: [{ set: { [o.id]: "on", ...Object.fromEntries(controls.map(([id, [on]]) => [id, on])) } }, { sound: "click" }] });
      R.push({ id: `${o.id}:off`, when: { interact: o.id }, if: { state: { [o.id]: "on" } }, then: [{ set: { [o.id]: "off", ...Object.fromEntries(controls.map(([id, [, off]]) => [id, off])) } }, { sound: "click" }] });
    }
  }
  return R;
}

const matches = (when, action) => (when.interact !== undefined ? action.interact === when.interact : action.use === when.use && action.on === when.on);

/**
 * Resolve an action against rules: the first rule whose `when` matches and whose `if` holds runs `then`; a rule whose
 * `when` matches but `if` fails runs its `else` (if any) and the search continues only when it has none.
 * Using an item nothing accepts gives a "nothing happens" message. Returns {state, events, rule}.
 */
export function resolve(action, rules, st) {
  if (action.use && !st.inventory.includes(action.use)) return { state: st, events: [{ type: "message", value: `you don't have the ${action.use}` }], rule: null };
  for (const r of rules) {
    if (!matches(r.when, action)) continue;
    if (check(r.if, st)) return { ...apply(r.then, st), rule: r.id };
    if (r.else) return { ...apply(r.else, st), rule: `${r.id}:else` };
  }
  if (action.use) return { state: st, events: [{ type: "message", value: `the ${action.use} does nothing here` }], rule: null };
  return { state: st, events: [], rule: null };
}

/** Problems a level's puzzle data has (also used by the level editor): unknown objects or items, items nothing uses. */
export function lintPuzzle(level) {
  const objects = objectsFromLevel(level), ids = new Set(objects.map(o => o.id)), problems = [];
  const rules = [...(level.puzzle || []), ...builtinRules(objects)];
  const items = new Set([...(level.hotspots || []).filter(h => h.item && !h.purpose).map(h => h.item),   // purpose (e.g. "distract"): not a puzzle item
 ...objects.flatMap(o => o.contains), ...rules.flatMap(r => [...(r.then || []), ...(r.else || [])]).filter(e => e.give).map(e => e.give)]);
  const used = new Set([...rules.map(r => r.when.use).filter(Boolean), ...(level.exit_needs || [])]);
  for (const r of rules) {
    const on = r.when.interact ?? r.when.on;
    if (!ids.has(on)) problems.push(`rule ${r.id}: no object "${on}"`);
    for (const e of [...(r.then || []), ...(r.else || [])]) for (const id of Object.keys(e.set || {})) if (!ids.has(id)) problems.push(`rule ${r.id}: sets unknown object "${id}"`);
  }
  for (const i of items) if (!used.has(i)) problems.push(`item "${i}" is never used by a puzzle`);
  for (const u of used) if (!items.has(u) && !(level.hotspots || []).some(h => h.item === u)) problems.push(`rule needs item "${u}" that the level never gives`);
  return problems;
}

/** Closed and locked doors with `blocks` as static bodies: characters with a radius stop at them; open doors let them pass. */
export class ObjectBodies {
  constructor(world, objects, getState, surfaceOf) {
    this.list = objects.filter(o => o.kind === "door" && o.blocks).map(o => ({ id: o.id, x: o.x, radius: o.width / 2, surface: surfaceOf(o), state: "idle", isObject: true,
      get passable() { return getState().states[o.id] === "open"; }, emit() {} }));
    world.bodies.push(...this.list);
  }
}

/** Save / load a puzzle state (plus anything else the page adds) in localStorage; every call is safe without storage. */
export const store = {
  save(key, data) { try { globalThis.localStorage?.setItem(key, JSON.stringify(data)); return true; } catch { return false; } },
  load(key) { try { const t = globalThis.localStorage?.getItem(key); return t ? JSON.parse(t) : null; } catch { return null; } },
  clear(key) { try { globalThis.localStorage?.removeItem(key); } catch { /* storage blocked */ } },
};

/** Placeholder drawing of an object in its state, standing on floor y (world coordinates). */
export function drawObject(ctx, o, state, y, { label = true } = {}) {
  ctx.save();
  if (o.kind === "door") {
    if (state === "open") { ctx.strokeStyle = "#8b6a4a"; ctx.lineWidth = 3; ctx.strokeRect(o.x - o.width / 2, y - o.height, o.width, o.height); }
    else { ctx.fillStyle = "#8b6a4a"; ctx.fillRect(o.x - o.width / 2, y - o.height, o.width, o.height); }
    if (state === "locked") { ctx.fillStyle = "#eda100"; ctx.fillRect(o.x - 7, y - 80, 14, 12); ctx.strokeStyle = "#eda100"; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(o.x, y - 80, 5, Math.PI, 0); ctx.stroke(); }
  } else if (o.kind === "chest") {
    ctx.fillStyle = "#9a6b3c"; ctx.fillRect(o.x - o.width / 2, y - o.height, o.width, o.height); ctx.fillStyle = "#7a5a3a";
    if (state === "open") { ctx.save(); ctx.translate(o.x - o.width / 2, y - o.height); ctx.rotate(-1.1); ctx.fillRect(0, -10, o.width, 10); ctx.restore(); }
    else ctx.fillRect(o.x - o.width / 2 - 3, y - o.height - 10, o.width + 6, 12);
  } else if (o.kind === "lever") {
    ctx.fillStyle = "#666"; ctx.fillRect(o.x - 14, y - 10, 28, 10);
    ctx.strokeStyle = state === "on" ? "#1baf7a" : "#c81e28"; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(o.x, y - 8); ctx.lineTo(o.x + (state === "on" ? 22 : -22), y - o.height); ctx.stroke();
  } else if (o.kind === "lamp") {
    ctx.fillStyle = "#555"; ctx.fillRect(o.x - 3, y - o.height, 6, o.height);
    ctx.fillStyle = state === "on" ? "#ffd54a" : "#999"; ctx.beginPath(); ctx.arc(o.x, y - o.height, 11, 0, 7); ctx.fill();
  }
  if (label) { ctx.fillStyle = "#333"; ctx.font = "11px system-ui"; ctx.fillText(`${o.id}: ${state}`, o.x - 26, y + 16); }
  ctx.restore();
}

/** A lamp that is off darkens its `lights` span (a flat placeholder overlay, not lighting). */
export function drawDarkness(ctx, objects, states, groundY) {
  for (const o of objects) if (o.kind === "lamp" && o.lights && states[o.id] !== "on") {
    ctx.fillStyle = "rgba(20,20,30,0.72)"; ctx.fillRect(o.lights[0], 0, o.lights[1] - o.lights[0], groundY);
  }
}
