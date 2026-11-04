// node runtime/bench/alloc.mjs [seconds]
// Simulates the sandbox hot loop (Ren + 10 guards with brains, scene drawables, emotes) at the runtime's fixed 240 Hz step
// for N simulated seconds with a no-op canvas, and reports minor GCs (scavenges) and heap growth: a proxy for per-frame
// allocation. Lower is better; compare before/after a change on the same machine.
import { PerformanceObserver } from "node:perf_hooks";
import { makeClip, World, Character, makeStepper } from "../anim.js";
import { GuardBrain } from "../behaviour.js";
import { sceneFromLevel, sceneDrawables } from "../scene.js";
import { Emotes } from "../emote.js";

const secs = +(process.argv[2] ?? 60);
const frame = (t = 0) => ({ rect: [0, 0, 20, 40], offset: [-10, -40], duration_ms: 83.3, travel_px: t, contacts: { foot_l: { x: 0, y: 0, state: "planted" } } });
const base = { format: "workbench-export/1", anchor: [0, 0], scale: 0.48, cell_size: [64, 64] };
const clip = (k, n, t) => makeClip(k, { ...base, frames: Array.from({ length: n }, () => frame(t)) });
const clips = { idle: clip("idle", 6, 0), walk: clip("walk", 14, 37), angry: clip("angry", 14, 0), eat: clip("eat", 14, 0) };
const level = { floors: [{ id: "A", x0: 0, x1: 4000, y: 470 }], hiding_spots: [{ id: "c", on: "A", x0: 500, x1: 590, height: 110 }],
                occluders: [{ id: "p", x0: 900, x1: 940, y0: 100, y1: 470 }], doors: [{ id: "d", on: "A", x: 3900, kind: "exit" }] };
const world = new World({ floors: [{ id: "A#0", x0: 0, x1: 4000, y: 470, left: "edge", right: "edge" }] });
const ren = new Character({ id: "ren", clips, world, x: 100, surface: "A#0" });
ren.silent = true;   // not heard either: the guards keep patrolling, so the loop is the same for the whole run
const guards = Array.from({ length: 10 }, (_, i) => new Character({ id: `g${i}`, clips, world, x: 300 + i * 350, surface: "A#0", radius: 34 }));
const brains = guards.map((g, i) => new GuardBrain({ guard: g, world, config: { patrol: [200 + i * 350, 450 + i * 350], wait_at_ends_ms: 800, vision: { range: 1 } } }));   // sight still runs; nobody is caught
const scene = sceneFromLevel(level), emotes = new Emotes({ ren });
const ctx = new Proxy({}, { get: () => () => {}, set: () => true });   // a canvas that does nothing
let t = 0;
const step = makeStepper(dt => {
  t += dt;
  if (!ren.busy) ren.walkTo(ren.x < 2000 ? 3800 : 100);
  for (const b of brains) b.update(dt, ren);
  ren.update(dt); for (const g of guards) g.update(dt); emotes.update(dt);
});
let minor = 0, major = 0;
new PerformanceObserver(list => { for (const e of list.getEntries()) { if (e.detail?.kind === 1 || e.kind === 1) minor++; else major++; } }).observe({ entryTypes: ["gc"] });
const h0 = process.memoryUsage().heapUsed;
for (let ms = 0; ms < secs * 1000; ms += 1000 / 60) {   // 60 Hz display frames
  step(1000 / 60);
  for (const it of sceneDrawables(scene, [ren, ...guards], { label: false })) it.draw(ctx);
}
await new Promise(r => setTimeout(r, 50));
console.log(JSON.stringify({ simulated_s: secs, minor_gcs: minor, major_gcs: major, heap_growth_kb: Math.round((process.memoryUsage().heapUsed - h0) / 1024) }));
