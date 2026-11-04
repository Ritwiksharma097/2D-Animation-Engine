// node --test runtime/test/objects.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { makeClip, World, Character } from "../anim.js";
import { objectsFromLevel, initialState, check, apply, builtinRules, resolve, lintPuzzle, ObjectBodies } from "../objects.js";

const LEVEL = {
  floors: [{ id: "A", x0: 0, x1: 1200, y: 470 }],
  hotspots: [],
  objects: [
    { id: "gate", kind: "door", x: 500, on: "A", state: "closed", blocks: true },
    { id: "lever1", kind: "lever", x: 200, on: "A", controls: { gate: ["open", "closed"] } },
    { id: "chest", kind: "chest", x: 700, on: "A", contains: ["key"] },
    { id: "door", kind: "door", x: 1000, on: "A", state: "locked", locked_by: "key", consume: true, blocks: true },
    { id: "lamp", kind: "lamp", x: 300, on: "A" }],
  puzzle: [{ id: "lamp_needs_lever", when: { interact: "lamp" }, if: { not: { state: { lever1: "on" } } }, then: [{ message: "no power" }] }],
};
const setup = () => { const objs = objectsFromLevel(LEVEL); return { objs, rules: [...LEVEL.puzzle, ...builtinRules(objs)], st: initialState(objs) }; };

test("conditions: flags, has / lacks, state lists, all / any / not, empty", () => {
  const st = { states: { d: "open", l: "on" }, flags: { a: true }, inventory: ["key"] };
  assert.equal(check(null, st), true); assert.equal(check({}, st), true);
  assert.equal(check({ flags: { a: true } }, st), true); assert.equal(check({ flags: { b: true } }, st), false);
  assert.equal(check({ flags: { b: false } }, st), true);   // unset flags read as false
  assert.equal(check({ has: "key" }, st), true); assert.equal(check({ has: ["key", "coin"] }, st), false); assert.equal(check({ lacks: "coin" }, st), true);
  assert.equal(check({ state: { d: ["open", "closed"] } }, st), true); assert.equal(check({ state: { d: "locked" } }, st), false);
  assert.equal(check({ all: [{ has: "key" }, { state: { l: "on" } }] }, st), true); assert.equal(check({ any: [{ has: "x" }, { flags: { a: true } }] }, st), true);
  assert.equal(check({ not: { has: "key" } }, st), false);
});

test("effects: set, toggle, flag, give / take, events; the input state is not modified", () => {
  const st = { states: { d: "closed", l: "off" }, flags: {}, inventory: ["key"], taken: [] };
  const r = apply([{ set: { d: "open" } }, { toggle: "l" }, { flag: { x: 1 } }, { give: "coin" }, { take: "key" }, { message: "hi" }, { sequence: "s" }], st);
  assert.deepEqual(r.state.states, { d: "open", l: "on" }); assert.deepEqual(r.state.inventory, ["coin"]); assert.equal(r.state.flags.x, 1);
  assert.deepEqual(r.events.map(e => e.type), ["state", "state", "give", "take", "message", "sequence"]);
  assert.deepEqual(st.states, { d: "closed", l: "off" }); assert.deepEqual(st.inventory, ["key"]);
});

test("the puzzle: lever opens the gate, chest gives the key once, key unlocks the door and is used up", () => {
  let { rules, st } = setup(), r;
  r = resolve({ interact: "door" }, rules, st); assert.equal(r.events[0].value, "the door is locked");
  r = resolve({ use: "key", on: "door" }, rules, st); assert.match(r.events[0].value, /don't have the key/); assert.equal(r.state.states.door, "locked");   // no key yet
  r = resolve({ interact: "lamp" }, rules, st); assert.equal(r.rule, "lamp_needs_lever");                 // explicit rule wins
  st = resolve({ interact: "lever1" }, rules, st).state; assert.equal(st.states.gate, "open"); assert.equal(st.states.lever1, "on");
  r = resolve({ interact: "lamp" }, rules, st); assert.equal(r.rule, "lamp:on");                         // powered now
  st = resolve({ interact: "chest" }, rules, st).state; assert.deepEqual(st.inventory, ["key"]); assert.equal(st.states.chest, "open");
  r = resolve({ interact: "chest" }, rules, st); assert.equal(r.rule, null); assert.deepEqual(r.state.inventory, ["key"]);   // only once
  r = resolve({ use: "key", on: "door" }, rules, st); st = r.state;
  assert.equal(st.states.door, "closed"); assert.deepEqual(st.inventory, []); assert.equal(r.rule, "door:unlock");
  st = resolve({ interact: "door" }, rules, st).state; assert.equal(st.states.door, "open");
  assert.match(resolve({ use: "lamp_oil", on: "door" }, rules, { ...st, inventory: ["lamp_oil"] }).events[0].value, /does nothing here/);
  st = resolve({ interact: "lever1" }, rules, st).state; assert.equal(st.states.gate, "closed");        // lever back: gate shuts
});

test("else branches and rule order", () => {
  const rules = [{ id: "r", when: { interact: "o" }, if: { flags: { ok: true } }, then: [{ message: "yes" }], else: [{ message: "not yet" }] }];
  const st = { states: { o: "off" }, flags: {}, inventory: [] };
  assert.equal(resolve({ interact: "o" }, rules, st).events[0].value, "not yet");
  assert.equal(resolve({ interact: "o" }, rules, { ...st, flags: { ok: true } }).events[0].value, "yes");
});

test("lint finds unknown objects, items nobody uses, and items no one gives", () => {
  assert.deepEqual(lintPuzzle(LEVEL), []);
  const bad = { ...LEVEL, objects: [...LEVEL.objects, { id: "c2", kind: "chest", x: 1, on: "A", contains: ["coin"] }],
                puzzle: [{ id: "x", when: { use: "gem", on: "ghost" }, then: [{ set: { nope: "open" } }] }] };
  const p = lintPuzzle(bad).join("\n");
  assert.match(p, /no object "ghost"/); assert.match(p, /unknown object "nope"/); assert.match(p, /"coin" is never used/); assert.match(p, /needs item "gem"/);
});

test("a closed blocking door stops a walker; open, it lets him through", () => {
  const frame = t => ({ rect: [0, 0, 20, 40], offset: [-10, -40], duration_ms: 100, travel_px: t, contacts: {} });
  const base = { format: "workbench-export/1", anchor: [0, 0], scale: 1, cell_size: [64, 64] };
  const clips = { idle: makeClip("i", { ...base, frames: [frame(0)] }), walk: makeClip("w", { ...base, frames: [frame(10), frame(10)] }) };
  let { objs, st } = setup();
  const world = new World({ floors: [{ id: "A#0", x0: 0, x1: 1200, y: 470, left: "edge", right: "edge" }] });
  new ObjectBodies(world, objs, () => st, () => "A#0");
  const ren = new Character({ id: "ren", clips, world, x: 300, surface: "A#0", radius: 20 });
  ren.walkTo(800); for (let t = 0; t < 8000; t += 10) ren.update(10);
  assert.ok(ren.x < 500 - 20 - 12 + 10 && ren.x > 440, `stopped at ${ren.x}`);
  st = { ...st, states: { ...st.states, gate: "open" } };
  ren.walkTo(800); for (let t = 0; t < 8000; t += 10) ren.update(10);
  assert.ok(ren.x > 790, `passed to ${ren.x}`);
});
