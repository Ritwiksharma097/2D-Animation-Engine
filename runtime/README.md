# runtime/anim.js: the animation runtime

A vanilla ES module (no build step) that plays workbench exports (`out/export/<character>/<action>.json`
+ `.png`, format `workbench-export/1`). Logic has no DOM dependency; only `loadClip(s)`, `draw` and
`run` touch the browser. Used by `out/export/play.html` and `out/export/guard_demo.html`.

```js
import { loadClips, World, Character, adaptClimb, run } from "../../runtime/anim.js";

const clips = await loadClips("/out/export", ["ren/idle", "ren/walk_keypose", "ren/climb_up", "ren/climb_down", "ren/jump"]);
const world = new World({ floorY: 470, platforms: [{ id: "ledge", x0: 457, x1: 667, top: 376 }] });
const ren = new Character({ id: "ren", clips, world, x: 70,
  names: { idle: "ren/idle", walk: "ren/walk_keypose", climb_up: "ren/climb_up", climb_down: "ren/climb_down", jump: "ren/jump" } });
ren.walkTo(ren.climbStartX("climb_up", "ledge")).climbUp("ledge").walkTo(600);
ren.on("refused", e => console.warn(e.reason));
run([ren], () => { ctx.clearRect(0, 0, w, h); ren.draw(ctx); ren.drawDebug(ctx); });
```

## Clips
- `makeClip(key, json, img)` wraps an export (img may be `null` for tests); `loadClip(base, key)`,
  `loadClips(base, keys)` fetch JSON + sheet. Units: cell px in the clip, times `clip.scale` = game px.
- `frontExtent(clip)`: how far the drawings reach ahead of the anchor (game px).

## World
`new World({ floorY, platforms: [{id, x0, x1, top}], frontBandCell = 40 })`. `x0` is a platform's front
face. `limits(surface, walkClip, x)` gives the walkable range: on the floor, walking stops where the
walk drawings' front-most pixel reaches a face (a near limb may overlap 40 cell px, the same allowance
as `props.py`); on a platform, 10 px inside its edges. Platforms are plain objects; change `top` / `x0`
to move a ledge.

## Character
`new Character({ id, clips, world, x, surface = "floor", dir = 1, names, turnMs = 120 })`. `names`
maps roles (`idle`, `walk`, `climb_up`, `climb_down`, `jump`, and any one-shot like `eat`, `happy`)
to clip keys.

Commands queue and run in order; with an empty queue the character returns to `idle`
(its idle clip loops):

| command | does |
| --- | --- |
| `walkTo(x)` | turns first if needed, then walks with **contact-driven travel**: each frame advances by that frame's exported `travel_px` along the facing, so planted feet stay put. Stops on a frame boundary, never overshoots, never walks into a platform face. |
| `turn(dir)` | mirrors to face `dir` after `turnMs` (no turn drawings exist; it is a held pose). |
| `climbUp(platformId)`, `climbDown(platformId)` | the **ledge-height adapter**: `adaptClimb(clip, height)` picks the export's contact-pinned path for that height (`paths_by_height`). Heights outside the looser range are **refused** (event `refused`, queue cleared); pass `{strict: true}` to also refuse marginal heights. The climb starts at its designed position relative to the ledge face (`climbStartX(role, platformId)`). A walk that had to stop short shows as a step in (Ren: about 39 game px; an open owner decision). |
| `jumpTo(x, surface)` | uses the export's `jump` timing (takeoff frame, landing frame, arc height). |
| `play(role, {loops})` | a one-shot reaction (happy, eat, love...), then back to idle. |
| `wait(ms)`, `clear()` | |

State: `state` (`idle`, `walk`, `turn`, `climb`, `jump`, `play`, `wait`), `busy`, `x`, `y`, `dir`,
`surface`, `clip`, `k` (frame). `travelOverride` (cell px per frame) replaces contact travel, e.g. to
show the old 41.9 px/frame slide.

Events (`on(name, fn)`): `state` {from, to}, `frame` {clip, frame}, `done` {command}, `refused`
{command, reason}, `turn` {dir}, and **named clip events** from the export's `events`
(annotation documents declare them by 1-based drawing number), e.g. guard eating `pickup` (with a
world `point` where the drawn apple lies) and `bite`, Ren jump `takeoff` / `land`, Ren climb
`hands_on_ledge` / `on_top`.

Debug: `drawDebug(ctx)` draws planted (green) and free (orange) contacts and red pins where planted
contacts landed; `drift` / `maxDrift` report how far a planted contact has moved since landing.

## Tests
`node --test runtime/test/runtime.test.mjs` (8 tests: travel and drift, turning, stopping before a face, ladder cycles and rung error, adapter
supported / marginal / refused, climb path and refusal, jump arc and landing, one-shot events).
Browser checks: `python workbench/tests/play_checks.py` and `python workbench/tests/guard_demo_checks.py`.

# runtime/level.js: levels, navigation, camera

`compileLevel(levelJson)` gives walk regions (floors split by ledges; sides are `face` or `edge`),
platforms, ladders and hotspots. `worldFromLevel(compiled)` builds a `World`.
`navGraph(compiled, character)` lists transitions, each with `ok` / `reason`, judged from that
character's drawings:
- climb up / down on either face, via the ledge-height adapter;
- jumps, within `rules.jump_max_gap` / `jump_max_rise`;
- ladders, only with a ladder clip carrying rung data (and up only; there is no ladder-down).

`planRoute(compiled, edges, from, to)` finds the shortest route over ok transitions, or returns
`{ok:false, reason}` listing the refused ones. `goTo(compiled, edges, character, x, y)` turns a click
into a route and queues it. `Camera({viewW, levelW})` has `update(targetX, dtMs)` and `snap(x)`.
Tests: `node --test runtime/test/level.test.mjs`.

# runtime/behaviour.js: interactions and guard behaviour

Decisions are pure functions, so they can be tested without animation; the classes connect them to
Characters. All tuning is plain JSON.

- `canSee(eye, dir, target, {range, halfAngleDeg}, solids)`: vision cone plus line of sight
  (`segmentHitsRect`). `sightBlockers(compiled)` gives the solids of a level.
- `decideGuard(state, perception, dt, config)` returns `{state, actions}`. Modes: `patrol` ->
  `suspicious` (suspicion rises while he sees Ren and decays otherwise; at `suspicious_at` he looks
  around, and when it decays he plays `angry`, then patrols) -> `chase` (at `alert_at` while seeing
  Ren) -> `caught` (within `catch_range`). Food in `food.notice_range` sends him `distracted`
  (walk to it) -> `eating` -> `patrol`. `lovestruck` is a hook: it plays `love` and overrides
  everything until released. Defaults: `GUARD_DEFAULTS`.
- `GuardBrain({guard, config, world, solids})` runs it on a guard Character: patrol between
  `config.patrol` ends with `wait_at_ends_ms`. There is no guard look-around drawing, so
  "suspicious" alternates his facing. Events: `mode`, `suspicious`, `caught`, `ate`.
  `setFood(food, reach)` tells it about dropped food.
- `decideIdleHint(state, idle, dt, {after_ms})`: after standing idle that long, play `look_around`
  once (`hint: true`), as a hook for "looks at the player".
- `Interactions({hotspots, inventory, defs})`: `take(character, hotspotId)` walks so the clip's
  event point (e.g. Ren `interact` `pickup`, where his hand reaches the ground) lands on the item,
  plays the role, and moves the item to the `Inventory` at the event. `drop`, `throwItem` (lands
  after `flightMs`, emitting `landed`), `update(dt)`.

Tests: `node --test runtime/test/behaviour.test.mjs` (7).
