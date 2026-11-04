// node --test runtime/test/framerate.test.mjs : 30, 60 and 144 Hz must give the same positions (fixed timestep).
import test from "node:test";
import assert from "node:assert/strict";
import { makeClip, World, Character, makeStepper } from "../anim.js";
import { decideGuard } from "../behaviour.js";

const frame = (travel, contacts = {}, ms = 180) => ({ rect: [0, 0, 20, 40], offset: [-10, -40], duration_ms: ms, travel_px: travel, contacts });
const base = { format: "workbench-export/1", anchor: [0, 0], scale: 0.4777, cell_size: [64, 64] };
const walk = makeClip("w", { ...base, frames: [98, 70, 108, 81].map(t => frame(t)) });            // Ren's contact travel
const idle = makeClip("i", { ...base, frames: [frame(0)] });
const jump = makeClip("j", { ...base, frames: [0, 1, 2, 3, 4, 5].map(() => frame(0, {}, 83.3)), jump: { takeoff_after: 1, land_at: 4, arc_height_px: 102 } });

function simulate(hz, seconds) {
  const world = new World({ floorY: 470, platforms: [{ id: "far", x0: 700, x1: 1100, top: 470 }] });
  const c = new Character({ id: "ren", clips: { idle, walk, jump }, world, x: 50 });
  c.walkTo(600).jumpTo(800, "far").walkTo(1000);
  let gs = { mode: null, suspicion: 0 };
  const step = makeStepper(dt => { c.update(dt); gs = decideGuard(gs, { sees: c.x > 300 && c.x < 500, renX: c.x, guardX: 900, foodX: null }, dt).state; });
  const samples = [], frameMs = 1000 / hz;
  let t = 0, next = 250;
  while (t < seconds * 1000 - 1e-6) {
    step(frameMs); t += frameMs;
    if (t >= next - 1e-6) { samples.push([+(t / 1000).toFixed(3), +c.x.toFixed(3), +c.y.toFixed(3), c.state, +gs.suspicion.toFixed(4)]); next += 250; }
  }
  return samples;
}

test("same positions at 30, 60 and 144 Hz (sampled at shared times every 1/4 s ... compared on the 1 s marks)", () => {
  const at = s => s.filter(r => Number.isInteger(r[0]));
  const a = at(simulate(30, 12)), b = at(simulate(60, 12)), c = at(simulate(144, 12));
  assert.ok(a.length >= 11);
  assert.deepEqual(b, a); assert.deepEqual(c, a);
  assert.equal(a[a.length - 1][3], "idle"); assert.ok(Math.abs(a[a.length - 1][1] - 1000) < 30);
});
