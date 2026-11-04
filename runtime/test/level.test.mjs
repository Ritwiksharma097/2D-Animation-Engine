// node --test runtime/test/level.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { makeClip, Character } from "../anim.js";
import { compileLevel, worldFromLevel, navGraph, planRoute, goTo, surfaceAt, Camera } from "../level.js";

const frame = (travel, contacts = {}, ms = 100) => ({ rect: [0, 0, 20, 40], offset: [-10, -40], duration_ms: ms, travel_px: travel, contacts });
const base = { format: "workbench-export/1", anchor: [0, 0], scale: 1, cell_size: [64, 64] };
const walk = makeClip("t/walk", { ...base, frames: [0, 1, 2, 3].map(i => frame(10, { [i < 2 ? "foot_l" : "foot_r"]: { x: 15 - 10 * (i % 2), y: 0, state: "planted" } })) });
const idle = makeClip("t/idle", { ...base, frames: [frame(0)] });
const heights = {}; for (let p = 60; p <= 140; p++) heights[p] = { height: p, supported: p >= 95 && p <= 105, supported_2x: p >= 90 && p <= 110, front_x: 20, path: [[0, 0], [10, -p / 2], [40, -p]] };
const climb = k => makeClip(k, { ...base, frames: [frame(0), frame(0), frame(0)], paths_by_height: heights, height_rule: { strict_range_pct: [95, 105], loose_range_pct: [90, 110] } });
const down = k => makeClip(k, { ...base, frames: [frame(0), frame(0), frame(0)], paths_by_height: Object.fromEntries(Object.entries(heights).map(([p, e]) => [p, { ...e, front_x: -40, path: [[0, 0], [-20, p / 2], [-40, +p]] }])), height_rule: { strict_range_pct: [95, 105], loose_range_pct: [90, 110] } });
const jump = makeClip("t/jump", { ...base, frames: [0, 1, 2, 3].map(() => frame(0)), jump: { takeoff_after: 0, land_at: 3, arc_height_px: 10 } });
const ladder = makeClip("t/ladder", { ...base, frames: [0, 1, 2, 3].map(() => frame(0)), ladder: { rise_px: [10, 10, 10, 10], rise_px_per_cycle: 40, rung_spacing_px: 20 } });
const renClips = { idle, walk, climb_up: climb("t/up"), climb_down: down("t/down"), jump };
const guardClips = { ...renClips, ladder };

// floor A [0,1000] with a 100 px ledge L1 at 400-600 and a 200 px ledge L2 at 800-900; a 100 px gap; floor B [1100, 2000];
// a 120 px platform P above B reached by a ladder.
const level = { format: "workbench-level/1", name: "t", size: [2000, 400],
  floors: [{ id: "A", x0: 0, x1: 1000, y: 300 }, { id: "B", x0: 1100, x1: 2000, y: 300 }],
  ledges: [{ id: "L1", x0: 400, x1: 600, top: 200, on: "A" }, { id: "L2", x0: 800, x1: 900, top: 100, on: "A" }],
  platforms: [{ id: "P", x0: 1500, x1: 1800, top: 180 }], ladders: [{ id: "LD", x: 1450, from: "B", to: "P", rung_spacing: 20 }] };
const C = compileLevel(level);
const mk = (clips, x = 50) => new Character({ id: "c", clips, world: worldFromLevel(C), x, surface: "A#0" });
const run = (c, ms) => { for (let t = 0; t < ms; t += 10) c.update(10); };

test("ledges split floors into regions with face edges", () => {
  assert.deepEqual(C.regions.map(r => [r.id, r.x0, r.x1, r.left, r.right]),
    [["A#0", 0, 400, "edge", "face"], ["A#1", 600, 800, "face", "face"], ["A#2", 900, 1000, "face", "edge"], ["B#0", 1100, 2000, "edge", "edge"]]);
  assert.equal(surfaceAt(C, 500, 150).id, "L1"); assert.equal(surfaceAt(C, 500, 290).id, "L1"); assert.equal(surfaceAt(C, 300, 290).id, "A#0");
});

test("graph judges transitions from the drawings: L2 (200 px) is too high, the ladder needs ladder drawings", () => {
  const e = navGraph(C, mk(renClips));
  const f = (t, p) => e.filter(x => x.type === t && (x.platform === p || x.ladder === p));
  assert.ok(f("climb_up", "L1").every(x => x.ok)); assert.ok(f("climb_up", "L2").every(x => !x.ok));
  assert.match(f("climb_up", "L2")[0].reason, /outside/);
  assert.ok(e.some(x => x.type === "jump" && x.from === "A#2" && x.to === "B#0" && x.ok));
  assert.ok(f("ladder", "LD").every(x => !x.ok));
  assert.ok(navGraph(C, mk(guardClips)).some(x => x.type === "ladder" && x.ok));
});

test("route over L1 (up the front, down the back) and execute it", () => {
  const c = mk(renClips); const e = navGraph(C, c);
  const r = planRoute(C, e, { surface: "A#0", x: 50 }, { surface: "A#1", x: 700 });
  assert.ok(r.ok, r.reason);
  assert.deepEqual(r.steps.map(s => s.type + (s.side ? ":" + s.side : "")), ["walk", "climb_up:front", "walk", "climb_down:back", "walk"]);
  goTo(C, e, c, 700, 290); run(c, 30000);
  assert.equal(c.surface, "A#1"); assert.ok(Math.abs(c.x - 700) <= 10, `x ${c.x}`);
});

test("unreachable region behind a too-high ledge is refused with the reason", () => {
  const e = navGraph(C, mk(renClips));
  const r = planRoute(C, e, { surface: "A#1", x: 700 }, { surface: "A#2", x: 950 });
  assert.equal(r.ok, false); assert.match(r.reason, /L2/);
});

test("guard routes to the platform by ladder; Ren is refused", () => {
  const g = mk(guardClips, 1200); g.surface = "B#0";
  const ge = navGraph(C, g);
  const r = planRoute(C, ge, { surface: "B#0", x: 1200 }, { surface: "P", x: 1600 });
  assert.ok(r.ok); assert.deepEqual(r.steps.map(s => s.type), ["walk", "ladder", "walk"]);
  goTo(C, ge, g, 1600, 170); run(g, 60000); assert.equal(g.surface, "P");
  const ren = mk(renClips, 1200); ren.surface = "B#0";
  assert.equal(planRoute(C, navGraph(C, ren), { surface: "B#0", x: 1200 }, { surface: "P", x: 1600 }).ok, false);
});

test("camera follows with a dead zone and clamps to the level; easing is frame-rate independent", () => {
  const a = new Camera({ viewW: 800, levelW: 2000 }), b = new Camera({ viewW: 800, levelW: 2000 });
  for (let i = 0; i < 60; i++) a.update(1500, 1000 / 60);
  for (let i = 0; i < 144; i++) b.update(1500, 1000 / 144);
  assert.ok(Math.abs(a.x - b.x) < 2, `${a.x} vs ${b.x}`);
  for (let i = 0; i < 600; i++) a.update(1990, 16.7);
  assert.equal(Math.round(a.x), 1200);
});
