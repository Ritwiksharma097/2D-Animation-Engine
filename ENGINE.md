# ENGINE.md: overview for the next assistant or collaborator

This repo is a **2D sprite animation workbench plus a small runtime** for a point-and-click game. It
diagnoses drawings (it never redraws them), stores fixes as data, exports clean clips, and plays them
in browser pages. It is not the game: there is no story, setting or real level here.

Read this first. Then use `PROGRESS.md` for step-by-step history and known problems, `FORMAT.md` for
every JSON format, `REPORT.md` for what the analysis found, `README.md` for commands, and
`runtime/README.md` for the JS API.

## 1. Architecture and data flow

```
assets/                    source art + manifest (read only, never written)
   │   NN.png frames per action, assets/manifest.json (status, owner feedback, cell size, old scenes)
   ▼
annotations/               everything a person (or the tools) decided about the art
   │   <char>/<action>.json  contacts per frame, edits (order, holds, drops, durations, offsets,
   │                         snap to ground, mirror), scene (props + path), events (e.g. pickup)
   │   <char>/_identity.json identity regions (hood, face, tabard ...)
   │   _settings.json        owner decisions: game_scale, travel overrides, open decisions
   │   _reviews.json         owner verdicts and comments from the review page
   ▼
workbench/*.py             analysis (reads assets + annotations, writes out/)
   │   analyze.py            metrics + report.json per action (edits applied, contacts preferred)
   │   diagnostics.py        PNGs: contact sheet, onion skin, world strip, charts, identity side-by-side
   │   props.py ledge_sweep.py ladder.py   scenes, ledge-height range, ladder cycles
   │   regions.py            per-region identity;  specs.py spec_check.py  redraw targets + checks
   │   intake.py             new sheets/frames -> incoming/ (never assets/);  krita_export.py  Krita packs
   ▼
workbench/export.py        out/export/<char>/<action>.json + .png (format workbench-export/1):
   │                       packed sheet, frame rects/offsets/durations, travel_px per frame, contacts,
   │                       anchor, scale, events, climb paths by height, jump timing, ladder block
   ▼
runtime/                   vanilla ES modules, no build step, no DOM in the logic
   │   anim.js               clips, World, Character state machine, contact-driven travel, mirroring,
   │                         ledge-height adapter, ladders, events, debug overlay, fixed-step run()
   │   level.js              level compile, navigation graph, route planner, camera
   │   behaviour.js          vision cone + line of sight, guard brain, idle hint, inventory, hotspots
   ▼
levels/<name>.json         level format workbench-level/1 (floors, ledges, platforms, ladders, hotspots)
   ▼
pages                      out/export/play.html (Ren playtest), guard_demo.html, level_play.html,
                           sandbox/index.html (+ tuning.json);  dist/ = static copy for any host
```

Tool pages served by `python workbench/serve.py` (or `start_workbench.bat` on Windows):
`workbench/review.html` (owner review of every action), `workbench/index.html` (frame workbench:
play/scrub, onion skin, contact editing, edits, scenes), `workbench/regions.html` (identity regions),
`workbench/level_editor.html` (levels, transitions coloured green/red per character).

Key rules the pipeline keeps:
- **`assets/` is never written.** Fixes live in `annotations/`; generated files in `out/`; new art in
  `incoming/` until the owner moves it (a manual step).
- **Travel comes from contacts.** A walk's per-frame travel is derived from the planted foot, so the
  exported walk cannot slide. A travel override (settings) is the only exception and the runtime
  shows the resulting slide in red in the debug overlay.
- **The runtime refuses what the drawings can't do**: unsupported ledge heights, jumps beyond the
  level rules, ladders without rung data. The planner routes around refused transitions or reports why.
- **Analysis flags "suspect", never "pass"**, and every heuristic states its limits in its report.

## 2. How to add things

### A character
1. Frames: `assets/<char>/<action>/NN.png` (1-based, transparent RGBA, one cell size per action) and
   an entry in `assets/manifest.json` under `characters.<char>` (`identity_reference`, `actions`
   with `dir`, `frames`, `status`, `feedback`, `cell_size` if not the default). This is the owner's
   step (or `tools/import_from_gpt.py` on their PC); the tools never edit `assets/`. New art from
   generation or Krita should go through `python workbench/intake.py` into `incoming/` first.
2. Scale: add `characters.<char>.game_scale` to `annotations/_settings.json` with `confirmed: false`
   until the owner sets it (review page). Export reads it.
3. Identity regions: click them in `workbench/regions.html` (saved to `annotations/<char>/_identity.json`).
4. `python workbench/analyze.py --all` then check the review page.

### An action
1. Frames in `assets/` + manifest entry (as above), or through intake into `incoming/`.
2. Analyse: `python workbench/analyze.py <char> <action>`; read `out/<char>/<action>/` PNGs.
3. Annotate in the workbench (`#a=<char>/<action>`): contacts (click; drag to move; shift-click to
   delete), edits, a scene for climbs/ladders, events (e.g. `pickup`). Saved to
   `annotations/<char>/<action>.json`.
4. Export: `python workbench/export.py <char> <action>` (`--demo` re-exports everything the demo
   pages use).
5. Use it: give the Character a role name for it, e.g.
   `names: { walk: "ren/walk_keypose", happy: "ren/happy" }`, then `ch.play("happy")` or the matching
   command. Roles the state machine knows: `idle`, `walk`, `turn`, `climb_up`, `climb_down`, `jump`,
   `ladder`; anything else is a one-shot that returns to idle. Frame events arrive via `ch.on(name, fn)`.

### A level
1. Open `workbench/level_editor.html` through `serve.py`, start from `levels/demo.json`, drag/resize
   floors, ledges, platforms, ladders and hotspots, and check the transitions turn green for the
   character. Save writes `levels/<name>.json` (`POST /api/level?name=`). Format: `FORMAT.md` "Levels".
2. Play it: `out/export/level_play.html?level=../../levels/<name>.json`.
3. In code: `compileLevel(json)` → `worldFromLevel(C)` → `navGraph(C, character)` → `goTo(C, edges,
   character, x, y)` on a click; `Camera` for levels wider than the view.
4. Game-like rules (guard config, cover, exits, throw range) are page data, as in
   `sandbox/tuning.json`.

### Ship it
`python workbench/build_dist.py` copies runtime, exports, levels and sandbox into `dist/`; serve that
folder from any static host. Re-run after re-exporting.

## 3. Where each owner decision lives

All recorded in `annotations/_settings.json` (`open_decisions` names each one's place); none decided
by the tools.

| Decision | Status | Where to change it |
| --- | --- | --- |
| Guard game scale (relative to Ren) | **unconfirmed** (assumed equal to Ren's 0.4777) | `_settings.json` `characters.guard.game_scale`, or the review page |
| Ren game scale | confirmed 0.4777 | `_settings.json` `characters.ren` |
| Guard ledge reading (which ledge height his climb means) | open | `annotations/guard/climb_up.json` `scene` (`props[0].top_y`) |
| Ren's climb step-in (walk stops ~39 game px short of the climb start) | open | `out/export/play.html` `CLIMB_START` |
| Ren walk timing (180 ms per frame) | open | `annotations/ren/walk_keypose.json` `frames[].duration_ms` |
| Guard walk placeholder speed (37.21 px/frame; his feet slide) | open, unconfirmed | `_settings.json` `travel_overrides["guard/walk"]` (delete to return to contact-derived travel) |
| Commission new frames (guard walk, Ren in-betweens, guard ladder) | open | specs in `specs/*.png/json`; new art via `workbench/intake.py` into `incoming/` |
| Verdict per action | per action | review page → `annotations/_reviews.json` |
| Moving approved new art into `assets/` | owner only | manual copy + manifest edit |

## 4. Verified on the owner's PC, and not

Checked on the owner's Windows 11 PC by the local assistant (Python 3.14.3, Node 24), per `PROGRESS.md`:
- **Phase 1:** pytest; `analyze.py --all`; charts and keypose strip read and agree with the report;
  workbench moving preview with contact markers, no console errors.
- **Phase 2:** 23 tests; `--all` analyses 19 actions; playtest walk + climb; found the straight-line
  climb-path mistake (corrected in phase 3) and the walk-into-ledge bug (fixed).
- **Phase 3:** 24 tests; `start_workbench.bat` opens the review page; review page and playtest load;
  guard idle before/after looked at. Issues found then (404 probes, no "preparing" notice, overlap,
  guard scale) were fixed in phase 4.
- **Phase 4:** 27 tests; `node --test runtime/test/runtime.test.mjs`; guard demo (food, eat);
  `krita_export.py` builds a pack. Krita's own import steps were **not** confirmed (a headless
  `kritarunner` attempt didn't run the script).

**Not yet checked on the owner's PC: all of phase 5** (steps 23–28): travel override + red drift, the
Ren reactions report, levels/planner/camera/level editor, guard AI and interactions, the mechanics
sandbox, preload/touch/DPR/pause, `dist/`. These were verified in the cloud only: Node tests
(`node --test runtime/test/<file>.test.mjs` for each file; 24 pass), pytest, and Playwright scripts
in `workbench/tests/` (`level_checks`, `sandbox_checks`, `robustness_checks`, `play_checks`,
`guard_demo_checks`, ...) with their screenshots looked at. Touch was tested with an emulated
touchscreen and pause with a faked `document.hidden`, not a real phone or tab switch.

Never verified anywhere: the Krita menu round trip; any real-device mobile use; the drawings
themselves (the tools measure; whether motion looks right is the owner's judgement).

## 5. Known limits worth knowing before building on it

- Most animations are not owner-approved (the sandbox HUD names them). The guard walk is rejected
  and walks in place; Ren's approved walk has only 4 drawings and looks choppy at any travel.
- Only `sandbox/` uses the DPR-aware canvas and pointer input; the other demo pages scale a fixed
  canvas with CSS and use clicks.
- The guard can't climb or use ladders in the AI (his climb drawings are unjudged/unconfirmed), so a
  chase stops at a ledge face. Ladder-down has no drawings, so ladders are one-way up.
- Vision is a 2D cone to Ren's mid-body with line of sight blocked by props; very close below the
  guard's eye line reads as "outside the cone".
- Heuristics (foot clusters, palette, proportions) have documented false positives; see `PROGRESS.md`
  "Known problems" and each report's `limits`.
