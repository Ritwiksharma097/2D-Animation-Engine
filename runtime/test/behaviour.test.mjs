// node --test runtime/test/behaviour.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { makeClip, World, Character } from "../anim.js";
import { canSee, segmentHitsRect, decideGuard, decideIdleHint, Interactions, GUARD_DEFAULTS } from "../behaviour.js";

test("vision: range, cone, behind, and line of sight blocked by a prop", () => {
  const v = { range: 300, halfAngleDeg: 30 };
  assert.equal(canSee({ x: 0, y: 0 }, 1, { x: 200, y: 20 }, v).seen, true);
  assert.equal(canSee({ x: 0, y: 0 }, -1, { x: 200, y: 20 }, v).reason, "behind");
  assert.equal(canSee({ x: 0, y: 0 }, 1, { x: 400, y: 0 }, v).reason, "out of range");
  assert.equal(canSee({ x: 0, y: 0 }, 1, { x: 100, y: 150 }, v).reason, "outside the cone");
  const r = canSee({ x: 0, y: 0 }, 1, { x: 250, y: 30 }, v, [{ id: "crate", x0: 100, x1: 150, y0: -40, y1: 80 }]);
  assert.equal(r.reason, "blocked"); assert.equal(r.by, "crate");
  assert.equal(segmentHitsRect({ x: 0, y: 0 }, { x: 10, y: 0 }, { x0: 20, x1: 30, y0: -5, y1: 5 }), false);
});

const step = (s, p, ms = 100, n = 1) => { let out = { state: s, actions: [] }, all = []; for (let i = 0; i < n; i++) { out = decideGuard(out.state, p, ms); all.push(...out.actions); } return { state: out.state, actions: all }; };
const P = (o = {}) => ({ sees: false, renX: 0, guardX: 0, foodX: null, ...o });

test("guard: a glimpse makes him suspicious, sustained sight makes him chase and catch", () => {
  let r = step({}, P());
  assert.equal(r.state.mode, "patrol");
  r = step(r.state, P({ sees: true, renX: 300 }), 100, 3);           // 0.3 s seen -> suspicion 0.45
  assert.equal(r.state.mode, "suspicious"); assert.ok(r.actions.some(a => a.do === "look"));
  r = step(r.state, P({ sees: true, renX: 300 }), 100, 5);           // -> past alert_at: chase
  assert.equal(r.state.mode, "chase"); assert.ok(r.actions.some(a => a.do === "walk" && a.x === 300));
  r = step(r.state, P({ sees: true, renX: 300, guardX: 260 }));       // within catch_range
  assert.equal(r.state.mode, "caught"); assert.ok(r.actions.some(a => a.do === "catch"));
});

test("guard: suspicion decays; he looks around, gets angry, returns to patrol", () => {
  let r = step({ mode: "suspicious", suspicion: 0.4, timer: 0 }, P(), 100, 40);   // 4 s unseen
  assert.equal(r.state.mode, "patrol");
  assert.deepEqual(r.actions.map(a => a.do + (a.role ? ":" + a.role : "")), ["play:angry", "patrol"]);
});

test("guard: food distracts him (walk to it, eat), then he patrols; out of range food is ignored", () => {
  let r = step({ mode: "patrol", suspicion: 0 }, P({ foodX: 400, guardX: 100 }));
  assert.equal(r.state.mode, "distracted"); assert.ok(r.actions.some(a => a.toFood && a.x === 400));
  r = step(r.state, P({ foodX: 400, guardX: 400, atFood: true }));
  assert.equal(r.state.mode, "eating"); assert.ok(r.actions.some(a => a.role === "eat"));
  r = step(r.state, P({ foodX: null, guardX: 400, doneEating: true }));
  assert.equal(r.state.mode, "patrol");
  assert.equal(step({ mode: "patrol", suspicion: 0 }, P({ foodX: 2000, guardX: 100 })).state.mode, "patrol");
});

test("guard: lovestruck is a hook that overrides everything until released", () => {
  let r = step({ mode: "patrol", suspicion: 0 }, P({ lovestruck: true, sees: true }));
  assert.equal(r.state.mode, "lovestruck"); assert.ok(r.actions.some(a => a.role === "love"));
  r = step(r.state, P({ lovestruck: false }));
  assert.equal(r.state.mode, "patrol");
});

test("Ren's idle hint fires once after the idle time and resets when he moves", () => {
  let s = {}, acts = [];
  for (let t = 0; t < 7000; t += 100) { const r = decideIdleHint(s, true, 100); s = r.state; acts.push(...r.actions); }
  assert.equal(acts.length, 1); assert.equal(acts[0].role, "look_around");
  s = decideIdleHint(s, false, 100).state; assert.equal(s.fired, false);
});

test("take an item at the interact pickup event: walk so the hand meets it, inventory, drop and throw", () => {
  const frame = (t = 0) => ({ rect: [0, 0, 20, 40], offset: [-10, -40], duration_ms: 100, travel_px: t, contacts: {} });
  const base = { format: "workbench-export/1", anchor: [0, 0], scale: 1, cell_size: [64, 64] };
  const clips = { idle: makeClip("i", { ...base, frames: [frame()] }), walk: makeClip("w", { ...base, frames: [frame(5), frame(5)] }),
    interact: makeClip("x", { ...base, frames: [frame(), frame(), frame(), frame()], events: { pickup: { frame: 2, point: [30, 0] } } }) };
  const c = new Character({ id: "ren", clips, world: new World({ floorY: 0 }), x: 0 });
  const I = new Interactions({ hotspots: [{ id: "h1", x: 100, on: "floor", item: "apple", use: "interact" }] });
  let takenAt = null; I.on("taken", e => { takenAt = c.k; });
  I.take(c, "h1");
  for (let t = 0; t < 5000; t += 10) c.update(10);
  assert.equal(c.x, 70); assert.equal(takenAt, 2); assert.ok(I.inventory.has("apple")); assert.equal(I.hotspots.length, 0);
  const h = I.drop(c, "apple"); assert.equal(h.x, 100); assert.equal(I.hotspots.length, 1);
  I.inventory.add({ id: "apple2" }); const landed = []; I.on("landed", e => landed.push(e.hotspot.x));
  I.throwItem(c, "apple2", 300, "floor"); I.update(700); assert.deepEqual(landed, [300]);
});

test("chase does not re-issue the walk every frame (that would restart the walk clip forever)", () => {
  let r = step({ mode: "chase", suspicion: 1.2, target: 300 }, P({ sees: true, renX: 310, guardX: 100 }), 16, 30);
  assert.equal(r.actions.filter(a => a.do === "walk").length, 0);
  r = step(r.state, P({ sees: true, renX: 360, guardX: 120 }));      // Ren moved 60 px: re-target once
  assert.equal(r.actions.filter(a => a.do === "walk").length, 1);
});
