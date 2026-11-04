// node --test runtime/test/sequence.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { makeClip, World, Character } from "../anim.js";
import { Sequences } from "../sequence.js";
import { Emotes } from "../emote.js";
import { Sounds } from "../sound.js";

const frame = (t = 0, ev) => ({ rect: [0, 0, 20, 40], offset: [-10, -40], duration_ms: 100, travel_px: t, contacts: {} });
const base = { format: "workbench-export/1", anchor: [0, 0], scale: 1, cell_size: [64, 64] };
const mk = () => ({ idle: makeClip("i", { ...base, frames: [frame()] }), walk: makeClip("w", { ...base, frames: [frame(10), frame(10)] }),
  wave: makeClip("x", { ...base, frames: [frame(), frame(), frame()], events: { hi: { frame: 1 } } }) });
const setup = defs => {
  const world = new World({ floorY: 0 }), clips = mk();
  const ren = new Character({ id: "ren", clips, world, x: 0 }), guard = new Character({ id: "guard", clips, world, x: 300, dir: -1 });
  const actors = { ren, guard }, emotes = new Emotes(actors), sounds = new Sounds();
  const seqs = new Sequences(defs, { actors, emotes, sounds, view: { w: 200 } });
  const tick = (ms, step = 10) => { for (let t = 0; t < ms; t += step) { seqs.update(step); ren.update(step); guard.update(step); emotes.update(step); } };
  return { ren, guard, emotes, sounds, seqs, tick };
};
const INTRO = { id: "intro", trigger: { on: "level_start" }, steps: [
  { do: "walk", who: "ren", x: 100 }, { do: "face", who: "ren", toward: "guard" }, { do: "emote", who: "guard", kind: "?", ms: 500 },
  { do: "camera", who: "guard", ms: 400 }, { do: "wait", ms: 300 }, { do: "play", who: "ren", role: "wave" }, { do: "sound", id: "chime" },
  { do: "fade", to: 1, ms: 200 }, { do: "flag", name: "met_guard" }, { do: "fade", to: 0, ms: 200 }] };

test("sequence runs every step in order: walk, face, emote, camera pan, wait, play, sound, fade, flag", () => {
  const { ren, emotes, sounds, seqs, tick } = setup([INTRO]);
  assert.ok(seqs.fire({ on: "level_start" })); assert.equal(seqs.running, true);
  tick(300); assert.ok(ren.x > 0 && ren.x < 100, `walking ${ren.x}`);
  tick(2000); assert.equal(ren.x, 100); assert.equal(emotes.log[0], "guard:?");
  assert.ok(seqs.current.cameraX !== null || seqs.current.i > 3);
  tick(4000);
  assert.equal(seqs.running, false); assert.equal(seqs.flags.met_guard, true); assert.deepEqual(sounds.log, ["chime"]);
  assert.equal(seqs.overlay, 0); assert.equal(seqs.cameraX, null);
  assert.equal(seqs.fire({ on: "level_start" }), null);          // once
});

test("camera pan eases to centre the target; fade ramps the overlay", () => {
  const { seqs, tick } = setup([{ id: "pan", trigger: { on: "level_start" }, steps: [{ do: "camera", x: 600, ms: 400 }, { do: "fade", to: 1, ms: 100 }, { do: "wait", ms: 1000 }] }]);
  seqs.fire({ on: "level_start" }); tick(200); const mid = seqs.cameraX;
  assert.ok(mid > 0 && mid < 500, `mid ${mid}`); tick(210); assert.equal(seqs.cameraX, 500);
  tick(50); assert.ok(seqs.overlay > 0.2 && seqs.overlay < 0.9); tick(60); assert.equal(seqs.overlay, 1);
});

test("skip applies every remaining end state at once", () => {
  const { ren, seqs, tick, emotes } = setup([INTRO]);
  seqs.fire({ on: "level_start" }); tick(100);
  assert.equal(seqs.skip(), true);
  assert.equal(seqs.running, false); assert.equal(ren.x, 100); assert.equal(ren.dir, 1); assert.equal(ren.busy, false);
  assert.equal(seqs.flags.met_guard, true); assert.equal(seqs.overlay, 0); assert.equal(emotes.active.length, 0);
});

test("triggers: hotspot and event ids, requires flags, non-skippable, one at a time", () => {
  const defs = [{ id: "door", trigger: { on: "hotspot", id: "door" }, requires: { has_key: true }, steps: [{ do: "wait", ms: 100 }] },
                { id: "alarm", trigger: { on: "event", name: "caught" }, skippable: false, once: false, steps: [{ do: "wait", ms: 100 }] }];
  const { seqs, tick } = setup(defs);
  assert.equal(seqs.fire({ on: "hotspot", id: "door" }), null);     // needs the key
  seqs.flags.has_key = true;
  assert.ok(seqs.fire({ on: "hotspot", id: "door" })); assert.equal(seqs.fire({ on: "event", name: "caught" }), null);   // busy
  tick(150); assert.ok(seqs.fire({ on: "event", name: "caught" })); assert.equal(seqs.skip(), false);
  tick(150); assert.ok(seqs.fire({ on: "event", name: "caught" }));   // once: false
});

test("sounds: event, state and frame keys; mute keeps logging but plays nothing", () => {
  const { ren, sounds } = setup([]);
  sounds.bind(ren, { "state:walk": "step", "hi": "hello", "frame:x:2": "end" });
  ren.walkTo(50).play("wave");
  for (let t = 0; t < 3000; t += 10) ren.update(10);
  assert.deepEqual(sounds.log, ["step", "hello", "end"]);
  sounds.setMuted(true); sounds.play("x"); assert.equal(sounds.muted, true); assert.equal(sounds.log.at(-1), "x");
});

test("emotes: one per actor, expire, unknown kinds refused", () => {
  const { emotes } = setup([]);
  emotes.show("ren", "!", 300); emotes.show("ren", "heart", 300); assert.equal(emotes.of("ren"), "heart"); assert.equal(emotes.active.length, 1);
  emotes.update(310); assert.equal(emotes.of("ren"), null);
  assert.throws(() => emotes.show("ren", "lol"));
});
