// Level validation for the editor (and tests): problems a level has before anyone plays it. Pure; give it the compiled
// level, the character's navigation edges and any other screens the doors lead to.
import { planRoute } from "./level.js";
import { objectsFromLevel, lintPuzzle } from "./objects.js";

const regionAt = (C, on, x) => C.regions.find(r => (r.id === on || r.floor === on) && r.x0 - 1 <= x && x <= r.x1 + 1)?.id
  ?? C.platforms.find(p => p.id === on)?.id ?? null;

/** Where the player starts: level.start {on, x}, or 50 px into the first walk region. */
export function startOf(level, C) {
  const s = level.start;
  if (s) return { surface: regionAt(C, s.on, s.x) ?? C.regions[0].id, x: s.x };
  return { surface: C.regions[0].id, x: C.regions[0].x0 + 50 };
}

/**
 * Returns [{kind, id, message}] for: unreachable hotspots / objects / hiding spots / doors / exits (no route with the
 * character's drawings), patrol paths through solids (a ledge face, a floor end, a closed blocking door), doors to
 * missing screens or missing doors, sequence triggers naming missing hotspots, and puzzle lint (items no puzzle uses...).
 * `others` maps level names to their JSON (screens the doors lead to); a name missing there is a missing screen.
 */
export function validateLevel(level, C, edges, { others = {}, knownLevels = null } = {}) {
  const P = [], start = startOf(level, C);
  const reach = (kind, id, on, x) => {
    const surface = regionAt(C, on, x);
    if (!surface) { P.push({ kind, id, message: `${kind} ${id}: not on a floor or platform ("${on}" at x ${x})` }); return; }
    const r = planRoute(C, edges, start, { surface, x });
    if (!r.ok) P.push({ kind, id, message: `${kind} ${id} is unreachable from the start: ${r.reason}` });
  };
  for (const h of level.hotspots || []) reach("hotspot", h.id, h.on, h.x);
  for (const o of objectsFromLevel(level)) reach("object", o.id, o.on, o.x);
  for (const h of level.hiding_spots || []) reach("hiding spot", h.id, h.on, (h.x0 + h.x1) / 2);
  for (const d of level.doors || []) reach(d.kind === "exit" ? "exit" : "door", d.id, d.on, d.x);
  // patrols: one walk region, inside the floor, no closed blocking door in the way
  const objs = objectsFromLevel(level);
  for (const p of level.patrols || []) {
    const lo = Math.min(p.x0, p.x1), hi = Math.max(p.x0, p.x1);
    const r = C.regions.find(r => (r.floor === p.on || r.id === p.on) && r.x0 <= lo && lo <= r.x1);
    if (!r) { P.push({ kind: "patrol", id: p.id, message: `patrol ${p.id}: starts off the floor "${p.on}" at x ${lo}` }); continue; }
    if (hi > r.x1) {
      const ledge = C.platforms.find(l => l.kind === "ledge" && l.front === r.id);
      P.push({ kind: "patrol", id: p.id, message: `patrol ${p.id} runs through ${r.right === "face" && ledge ? `ledge ${ledge.id}'s face at x ${r.x1}` : `the floor end at x ${r.x1}`}` });
    }
    for (const o of objs) if (o.kind === "door" && o.blocks && o.state !== "open" && o.x > lo && o.x < hi && (o.on === p.on || o.on === r.floor))
      P.push({ kind: "patrol", id: p.id, message: `patrol ${p.id} runs through door ${o.id}, which starts ${o.state}` });
  }
  // doors to other screens
  for (const d of level.doors || []) {
    if (d.kind === "exit" || !d.to) continue;
    const other = others[d.to.level];
    if (!other) { P.push({ kind: "door", id: d.id, message: `door ${d.id} leads to missing screen "${d.to.level}"${knownLevels ? "" : " (not loaded)"}` }); continue; }
    if (!(other.doors || []).some(x => x.id === d.to.door)) P.push({ kind: "door", id: d.id, message: `door ${d.id} leads to door "${d.to.door}", which screen "${d.to.level}" doesn't have` });
  }
  // sequence triggers
  const hs = new Set([...(level.hotspots || []).map(h => h.id), ...objs.map(o => o.id)]);
  for (const s of level.sequences || []) if (s.trigger?.on === "hotspot" && !hs.has(s.trigger.id)) P.push({ kind: "sequence", id: s.id, message: `sequence ${s.id} is triggered by missing hotspot "${s.trigger.id}"` });
  for (const m of lintPuzzle(level)) P.push({ kind: "puzzle", id: "", message: m });
  return P;
}
