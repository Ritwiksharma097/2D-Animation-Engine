// node --test runtime/test/validate.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { compileLevel } from "../level.js";
import { validateLevel, startOf } from "../validate.js";
import { Sequences } from "../sequence.js";

// a character that can only walk (no climb, jump or ladder drawings): navGraph edges are all refused, so use none
const edgesNone = [];
const LEVEL = {
  floors: [{ id: "A", x0: 0, x1: 1000, y: 470 }, { id: "B", x0: 1300, x1: 1800, y: 470 }],
  ledges: [{ id: "L1", x0: 600, x1: 700, top: 376, on: "A" }],
  start: { on: "A", x: 80 },
  hotspots: [{ id: "apple", x: 200, on: "A", item: "apple", purpose: "distract" }, { id: "far", x: 1500, on: "B", item: "gem" }],
  objects: [{ id: "gate", kind: "door", x: 300, on: "A", state: "closed", blocks: true }, { id: "chest", kind: "chest", x: 450, on: "A", contains: ["key"] }],
  patrols: [{ id: "p1", who: "guard", on: "A", x0: 100, x1: 500 }, { id: "p2", who: "guard", on: "A", x0: 400, x1: 800 }, { id: "p3", who: "guard", on: "A", x0: 750, x1: 1200 }],
  hiding_spots: [{ id: "crate", on: "A", x0: 380, x1: 420, height: 100 }],
  doors: [{ id: "D1", on: "A", x: 950, to: { level: "nowhere", door: "X" } }, { id: "D2", on: "A", x: 900, to: { level: "two", door: "Q" } }],
  sequences: [{ id: "s1", trigger: { on: "hotspot", id: "ghost" }, steps: [] }],
};

test("validation lists unreachable things, patrols through solids, bad doors, bad triggers and puzzle lint", () => {
  const C = compileLevel(LEVEL);
  const P = validateLevel(LEVEL, C, edgesNone, { others: { two: { doors: [{ id: "P" }] } } }).map(p => p.message);
  const has = re => assert.ok(P.some(m => re.test(m)), `${re} not in:\n${P.join("\n")}`);
  has(/hotspot far is unreachable/);                 // floor B: no jump drawings in this test
  has(/door D1 is unreachable/);                     // beyond the ledge (no climb)
  has(/patrol p1 runs through door gate, which starts closed/);
  has(/patrol p2 runs through ledge L1's face at x 600/);
  has(/patrol p3 runs through the floor end at x 1000/);
  has(/door D1 leads to missing screen "nowhere"/);
  has(/door D2 leads to door "Q", which screen "two" doesn't have/);
  has(/sequence s1 is triggered by missing hotspot "ghost"/);
  has(/item "key" is never used/); has(/item "gem" is never used/);
  assert.ok(!P.some(m => /apple/.test(m)), "an item with a purpose (distract) isn't a puzzle item");
  assert.ok(!P.some(m => /hotspot apple|object chest|hiding spot crate/.test(m)), "reachable things are not reported");
});

test("a clean level has no problems; start defaults to the first region", () => {
  const L = { floors: [{ id: "A", x0: 0, x1: 1000, y: 470 }], hotspots: [], doors: [{ id: "out", on: "A", x: 950, kind: "exit" }],
              patrols: [{ id: "p", on: "A", x0: 200, x1: 800 }] };
  const C = compileLevel(L);
  assert.deepEqual(validateLevel(L, C, edgesNone), []);
  assert.deepEqual(startOf(L, C), { surface: "A#0", x: 50 });
});

test("enter-region sequence triggers", () => {
  const s = new Sequences([{ id: "e", trigger: { on: "enter", x0: 100, x1: 200 }, steps: [{ do: "wait", ms: 1 }] }], { actors: {} });
  assert.equal(s.fire({ on: "enter", x: 50 }), null); assert.ok(s.fire({ on: "enter", x: 150 }));
});
