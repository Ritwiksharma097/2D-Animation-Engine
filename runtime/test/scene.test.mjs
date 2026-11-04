// node --test runtime/test/scene.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { makeClip, World, Character } from "../anim.js";
import { GuardBrain } from "../behaviour.js";
import { sceneFromLevel, parallaxX, depthSort, hidingSpotAt, updateHiding, doorAt, Fader, sceneDrawables } from "../scene.js";

const frame = (t = 0) => ({ rect: [0, 0, 20, 40], offset: [-10, -40], duration_ms: 100, travel_px: t, contacts: {} });
const base = { format: "workbench-export/1", anchor: [0, 0], scale: 1, cell_size: [64, 64] };
const clips = { idle: makeClip("i", { ...base, frames: [frame()] }), walk: makeClip("w", { ...base, frames: [frame(10), frame(10)] }),
  crouch: makeClip("c", { ...base, frames: [frame(), frame(), frame(), frame()] }) };
const LEVEL = { floors: [{ id: "A", x0: 0, x1: 1000, y: 400 }],
  hiding_spots: [{ id: "crate", on: "A", x0: 300, x1: 380, height: 70, reveal_radius: 40 }],
  doors: [{ id: "d1", on: "A", x: 950, to: { level: "b", door: "d0" } }],
  layers: [{ id: "hills", parallax: 0.3, rects: [{ x: 0, y: 200, w: 500, h: 200 }] }], occluders: [{ id: "pillar", x0: 600, x1: 640, y0: 100, y1: 400 }] };

test("parallax: a far layer moves less than the world", () => {
  assert.equal(parallaxX(100, 200, 0), 100); assert.equal(parallaxX(100, 200, 1), -100); assert.equal(parallaxX(100, 200, 0.3), 40);
});

test("depth sort: by depth, then feet y, stable for ties; a character hiding behind a spot is drawn before it", () => {
  const s = depthSort([{ id: "fg", depth: 50 }, { id: "a", depth: 0, y: 400 }, { id: "b", depth: 0, y: 300 }, { id: "bg", depth: -100 }, { id: "c", depth: 0, y: 400 }]);
  assert.deepEqual(s.map(x => x.id), ["bg", "b", "a", "c", "fg"]);
  const sc = sceneFromLevel(LEVEL), ren = { y: 400, draw() {}, id: "ren" };
  const order = sceneDrawables(sc, [ren], { label: false }).map(i => i.actor ? "ren" : i.depth);
  assert.ok(order.indexOf("ren") < order.indexOf(5), order.join(","));   // spot (depth 5) covers Ren
  assert.equal(order[order.length - 1], 50);                             // occluder in front of everything
});

test("hiding: a held 'hide' pose inside a spot hides Ren; the guard sees him only within the reveal radius", () => {
  const world = new World({ floors: [{ id: "A#0", x0: 0, x1: 1000, y: 400, left: "edge", right: "edge" }] }), sc = sceneFromLevel(LEVEL);
  const ren = new Character({ id: "ren", clips, world, x: 340, surface: "A#0", names: { crouch: "crouch" } });
  const guard = new Character({ id: "g", clips, world, x: 200, surface: "A#0", dir: 1 });
  const brain = new GuardBrain({ guard, config: { vision: { range: 400, halfAngleDeg: 40, eye_height: 100, target_height: 30 } }, world });
  assert.equal(brain.look(ren).seen, true);                     // standing: seen
  ren.pose("crouch", { frames: [0, 1, 2], tag: "hide" });
  for (let t = 0; t < 1000; t += 10) ren.update(10);
  assert.equal(ren.holding, true); assert.equal(ren.busy, false); assert.equal(ren.k, 2);
  assert.equal(updateHiding(ren, sc.hiding)?.id, "crate"); assert.equal(ren.silent, true);
  assert.match(brain.look(ren).reason, /hidden \(crate\)/);
  guard.x = 310; assert.equal(brain.look(ren).seen, true);       // 30 px away: close enough to see
  ren.walkTo(500); ren.update(10); updateHiding(ren, sc.hiding);   // a new command ends the hold
  assert.equal(ren.state, "walk"); assert.equal(ren.hidingIn, null);
});

test("spots and doors match a floor's walk regions; a fader switches at the dark point", () => {
  const sc = sceneFromLevel(LEVEL);
  assert.equal(hidingSpotAt(sc.hiding, "A#0", 350)?.id, "crate"); assert.equal(hidingSpotAt(sc.hiding, "A#0", 390), null);
  assert.equal(doorAt(sc.doors, "A#1", 960)?.id, "d1");
  const f = new Fader({ outMs: 100, inMs: 100 }); let mid = 0;
  f.start(() => mid++); f.update(50); assert.equal(f.alpha, 0.5); assert.equal(mid, 0);
  f.update(60); assert.equal(mid, 1); assert.ok(f.alpha > 0.9);
  f.update(100); assert.equal(f.busy, false); assert.equal(f.alpha, 0);
  assert.equal(f.start(() => {}), true);
});
