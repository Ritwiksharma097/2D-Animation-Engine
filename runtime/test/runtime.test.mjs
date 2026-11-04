// node --test runtime/test   (Node 18+; no DOM needed)
import test from "node:test";
import assert from "node:assert/strict";
import { makeClip, adaptClimb, World, Character } from "../anim.js";

const frame = (travel, contacts = {}, ms = 100) => ({ rect: [0, 0, 20, 40], offset: [-10, -40], duration_ms: ms, travel_px: travel, contacts });
const base = { format: "workbench-export/1", anchor: [0, 0], scale: 1, cell_size: [64, 64] };

// a 4-frame walk whose planted foot moves back exactly 10 px per frame (so 10 px/frame travel can't slide)
// (stance alternates: foot_l in frames 0-1, foot_r in frames 2-3, like a real two-step cycle)
const walk = makeClip("t/walk", { ...base, frames: [0, 1, 2, 3].map(i => frame(10, { [i < 2 ? "foot_l" : "foot_r"]: { x: 15 - 10 * (i % 2), y: 0, state: "planted" } })) });
const idle = makeClip("t/idle", { ...base, frames: [frame(0), frame(0)] });
const happy = makeClip("t/happy", { ...base, frames: [frame(0), frame(0), frame(0)], events: { cheer: { frame: 1 } } });
const heights = {}; for (let p = 60; p <= 140; p++) heights[p] = { height: 100 * p / 100, supported: p >= 95 && p <= 105, supported_2x: p >= 90 && p <= 110, front_x: 30, path: [[0, 0], [5, -50], [10, -100 * p / 100]] };
const climb = makeClip("t/climb_up", { ...base, frames: [frame(0), frame(0), frame(0)], path: [[0, 0], [5, -50], [10, -100]], paths_by_height: heights, height_rule: { strict_range_pct: [95, 105], loose_range_pct: [90, 110] } });
const jump = makeClip("t/jump", { ...base, frames: [0, 1, 2, 3, 4].map(() => frame(0)), jump: { takeoff_after: 0, land_at: 4, arc_height_px: 20 } });
const clips = { idle, walk, happy, climb_up: climb, jump };
const run = (c, ms) => { for (let t = 0; t < ms; t += 10) c.update(10); };

test("contact-driven walk: travel per frame, zero planted-foot drift, stops without overshoot", () => {
  const c = new Character({ id: "a", clips, world: new World({ floorY: 0 }), x: 0 });
  c.walkTo(43); run(c, 2000);
  assert.equal(c.state, "idle");
  assert.equal(c.x, 40);                       // 4 steps of 10; the 5th would pass the goal by more than half a step
  assert.equal(c.maxDrift, 0);
});

test("walking back turns (mirrors) first and travels the other way", () => {
  const c = new Character({ id: "a", clips, world: new World({ floorY: 0 }), x: 100 });
  const states = []; c.on("state", e => states.push(e.to));
  c.walkTo(60); run(c, 2000);
  assert.equal(c.dir, -1); assert.equal(c.x, 60); assert.ok(states.includes("turn"));
  assert.equal(c.maxDrift, 0);
});

test("floor walk stops before a platform face (front extent and the 40-cell-px band)", () => {
  const world = new World({ floorY: 0, platforms: [{ id: "L", x0: 200, x1: 300, top: -100 }] });
  const c = new Character({ id: "a", clips, world, x: 0 });
  c.walkTo(1000); run(c, 10000);
  const front = c.x + 10;                        // walk frames reach 10 px ahead of the anchor
  assert.ok(front <= 200 + 40, `front ${front}`);
  assert.ok(c.x > 150);
});

test("ledge adapter: supported, marginal, refused", () => {
  assert.equal(adaptClimb(climb, 100).ok, true);
  assert.equal(adaptClimb(climb, 108).marginal, true);
  const r = adaptClimb(climb, 130);
  assert.equal(r.ok, false); assert.match(r.reason, /outside the supported range/);
  assert.equal(adaptClimb(climb, 108, { strict: true }).ok, false);
});

test("climb up follows the height's path and ends on the platform; unsupported height is refused", () => {
  const world = new World({ floorY: 0, platforms: [{ id: "L", x0: 50, x1: 300, top: -100 }, { id: "H", x0: 400, x1: 600, top: -130 }] });
  const c = new Character({ id: "a", clips, world, x: 0 });
  c.climbUp("L"); run(c, 1000);
  assert.equal(c.surface, "L"); assert.equal(c.y, -100); assert.equal(c.x, 50 - 30 + 10);
  const refused = []; c.on("refused", e => refused.push(e.reason));
  const d = new Character({ id: "b", clips, world, x: 350 }); d.on("refused", e => refused.push(e.reason));
  d.climbUp("H").walkTo(0); run(d, 1000);
  assert.equal(d.surface, "floor"); assert.equal(refused.length, 1); assert.equal(d.x, 350, "queue cleared after a refusal");
});

test("jump lands on the target surface with an arc", () => {
  const world = new World({ floorY: 0, platforms: [{ id: "F", x0: 100, x1: 400, top: -50 }] });
  const c = new Character({ id: "a", clips, world, x: 0 });
  let peak = 0; c.on("frame", () => { peak = Math.min(peak, c.y); });
  c.jumpTo(150, "F"); run(c, 1000);
  assert.equal(c.surface, "F"); assert.equal(c.x, 150); assert.equal(c.y, -50); assert.ok(peak < -50);
});

test("one-shot reaction fires its named event and returns to idle", () => {
  const c = new Character({ id: "a", clips, world: new World({ floorY: 0 }), x: 0 });
  const seen = []; c.on("cheer", e => seen.push(e.frame)); c.on("done", e => seen.push(e.command.type));
  c.play("happy"); run(c, 1000);
  assert.deepEqual(seen, [1, "play"]); assert.equal(c.state, "idle");
});

test("ladder: whole cycles for the ladder height, ends on top, rung error from planted rung contacts", () => {
  const rf = (y) => frame(0, { hand_r: { x: 0, y, state: "planted", surface: "ladder_rung" } });
  // 4 frames rising 10 each (40 per cycle); the planted hand moves DOWN 10 per frame in the cell, i.e. stays on its rung
  const lad = makeClip("t/ladder", { ...base, frames: [-40, -30, -20, -10].map(rf), ladder: { rise_px: [10, 10, 10, 10], rise_px_per_cycle: 40, rung_spacing_px: 20 } });
  const world = new World({ floorY: 0, platforms: [{ id: "top", x0: 50, x1: 300, top: -120 }], ladders: [{ id: "L", x: 30, top: -120, rungSpacing: 20, toSurface: "top" }] });
  const c = new Character({ id: "g", clips: { ...clips, ladder: lad }, world, x: 0 });
  const ev = []; c.on("ladder_on", e => ev.push(["on", e.cycles])); c.on("ladder_off", () => ev.push(["off"]));
  let worst = 0; c.on("frame", () => { worst = Math.max(worst, c.rungError); });
  c.climbLadder("L"); run(c, 5000);
  assert.deepEqual(ev, [["on", 3], ["off"]]);   // 120 / 40 per cycle
  assert.equal(c.surface, "top"); assert.equal(c.y, -120); assert.equal(c.x, 30);
  assert.ok(worst < 0.01, `rung error ${worst}`);
});
