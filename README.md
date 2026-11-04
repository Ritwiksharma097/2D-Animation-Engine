# 2D animation workbench

**Owner: double-click `start_workbench.bat`** (Windows). It starts the server and opens the review
page, where every action can be watched, compared and given a verdict. The first start analyses
everything in the background (about a minute). Needs Python + `pip install -r requirements.txt` once.

Diagnoses sprite animation problems (sliding feet, repeated or uneven frames, identity drift) so they
can be found from still images and numbers instead of by watching playback. See `CLAUDE.md` for the
brief, `FORMAT.md` for the data formats, `PROGRESS.md` for status and `REPORT.md` for results.

Overview of the whole pipeline and runtime: [`ENGINE.md`](ENGINE.md).

## Setup (Windows or Linux, Python 3.13/3.14)

```
python -m venv .venv
.venv\Scripts\activate        (Windows)   |   source .venv/bin/activate   (Linux/macOS)
pip install -r requirements.txt
```

## Analyse an action

```
python workbench/analyze.py guard walk
python workbench/analyze.py ren walk_keypose --travel 41.9
python workbench/analyze.py --all          # every action in the manifest
python workbench/analyze.py --report-set   # the five in REPORT.md
```

Arguments are a character and action name from `assets/manifest.json`. `--travel` is the travel per
frame in cell pixels (otherwise taken from the annotation file or the manifest's `old_timing`).
`--no-annotations` ignores `annotations/` and uses the heuristics. `--no-images` skips PNGs.

Output goes to `out/<character>/<action>/report.json` (plus diagnostic PNGs). `summary` is plain
English; `flags` are only ever "suspect"; `limits` says what each heuristic cannot tell.

## Tests

```
python -m pytest workbench/tests
```

## Diagnostic images

`analyze.py` also writes PNGs next to the report (skip with `--no-images`): `contact_sheet.png`,
`onion.png`, `charts.png`, `identity.png` and, for walks, `world_strip.png` (at the given travel),
`world_strip_best_constant.png` and `world_strip_per_frame.png`. Each image explains its own
markings in its header.

## Browser workbench

```
python workbench/serve.py
```

Open http://localhost:8000/workbench/ . (Plain `python -m http.server` from the repo root also works,
at http://localhost:8000/workbench/, but then Save downloads the JSON instead of writing
`annotations/<character>/<action>.json`, and "Re-run analysis" is unavailable.)

- Pick an action; play / pause (Space), step (arrow keys), scrub; loop, ping-pong or once; edit each
  frame's duration under its thumbnail or set all at once.
- Onion skin: frames back (blue) / ahead (orange) and opacity.
- Preview "in place" or "moving across ground" with a ticked ground line. Travel: constant, the
  report's best constant, the report's per-frame values, or derived from planted contacts. In moving
  mode, red pins mark where each planted foot landed and a bar shows how far it has slid.
- Contacts: pause in place, pick a point name and state, click to place, drag to move, shift-click to
  delete. Save writes the action document (see FORMAT.md).
- Report flags and summary appear beside the timeline; click a flag to jump to its frame.
- "Compare side by side" opens a second viewer (play/pause can be synced).

Screenshots for visual checks: `python workbench/tests/screenshot_workbench.py` (needs
`pip install playwright` and `python -m playwright install chromium` on a fresh machine).

Interaction checks (assert drag, shift-click delete, ping-pong, durations):
`python workbench/tests/ui_checks.py`.

## Non-destructive edits

Order, holds, drops, durations, per-frame offsets, snap-to-ground and mirror are stored in
`annotations/<character>/<action>.json` (FORMAT.md, "Edits") and applied by analysis and the page.

```
python workbench/edits.py suggest-idle guard idle --write   # group near-duplicates into held poses
python workbench/edits.py snap guard walk --write           # feet onto ground_y
python workbench/analyze.py guard idle --no-annotations --tag original   # the "before" report
python workbench/analyze.py guard idle
```

Compare in the browser: http://localhost:8000/workbench/#a=guard/idle&b=guard/idle&b.raw=1&play=1

## Scenes: ledges and ladders

```
python workbench/props.py ren climb_up                   # check against the stored scene -> scene.png
python workbench/props.py ren climb_up --path contacts   # path derived from planted contacts
python workbench/tests/scene_checks.py                   # page screenshots + live edit check
```

In the page choose preview "scene". Ledge height / front and rung spacing are editable (live with
serve.py). New contacts get the surface chosen next to "on".

## Per-region identity

```
python workbench/regions.py init ren      # default seeds on the identity reference
python workbench/regions.py compare ren walk_keypose jump rejected_walk_flatboy
```

## Export for the game + playtest

```
python workbench/export.py --demo          # out/export/ren/*.png + *.json
python workbench/serve.py                  # then http://localhost:8000/out/export/play.html
python workbench/tests/play_checks.py      # walk/climb/jump checks with screenshots
```

## Ledge heights

```
python workbench/ledge_sweep.py ren climb_up     # supported range + ledge_<pct>.png scene images
python workbench/export.py --demo                # exports paths_by_height for the playtest slider
```

## Redraw specs

```
python workbench/specs.py all                                         # specs/*.png + *.json
python workbench/spec_check.py specs/guard_walk.json path\to\new_frames   # meets / MISSES per criterion
```

## Identity regions by clicking

http://localhost:8000/workbench/regions.html (with `serve.py`): click seeds on the identity
reference, Save, then Check any action. Test: `python workbench/tests/regions_checks.py`.

## Art intake (new frames)

```
python workbench/intake.py path\to\sheet.png --character guard --action walk_v2 --replaces walk --spec specs/guard_walk.json
python workbench/intake.py path\to\frames_folder --character ren --action walk_8 --replaces walk_keypose
```

Writes `incoming/<character>/<action>/` (never `assets/`); the review page shows it as "new, awaiting owner".

## Runtime ("engine")

`runtime/anim.js` plays exports in any page (API in `runtime/README.md`). Demos:
http://localhost:8000/out/export/play.html and http://localhost:8000/out/export/guard_demo.html.
Tests: `node --test runtime/test/runtime.test.mjs`.

## Ladders

```
python workbench/ladder.py check guard ladder_up --rungs 8   # rung landing, cycles, out/guard/ladder_up/ladder.png
python workbench/ladder.py spec                              # specs/guard_ladder.png redraw targets
```

## Krita round trip

`python workbench/krita_export.py ren walk_keypose --spec specs/ren_walk_inbetweens.json`, then follow
`out/krita/ren_walk_keypose/KRITA_STEPS.md` and bring the render back with `intake.py ... --as-is`.
See `KRITA.md` (why there is no `.kra` writer).

## Levels

- Play: http://localhost:8000/out/export/level_play.html (click anywhere; Ren routes there).
- Edit: http://localhost:8000/workbench/level_editor.html (save writes `levels/<name>.json`).
- Tests: `node --test runtime/test/level.test.mjs`, `python workbench/tests/level_checks.py`.

## Mechanics sandbox (not the game)

http://localhost:8000/sandbox/index.html; tuning in `sandbox/tuning.json`.
Test: `python workbench/tests/sandbox_checks.py`.

## Hub

`python workbench/serve.py` (or `start_workbench.bat`), then http://localhost:8000/ : one page linking
the review page, sandbox, demos, level editor, regions, specs and docs. Check of the phase 6 fixes:
`python workbench/tests/phase6_fixes_checks.py`.

## Static build (`dist/`)

```
python workbench/build_dist.py
```

Copies `runtime/`, `out/export/` (sheets, JSON, the three demo pages), `levels/` and `sandbox/` into
`dist/` with the same relative paths, plus `dist/index.html` linking the demos. It needs no server
code: serve it with any static host, e.g. `python -m http.server -d dist 8080`. Re-run it after
re-exporting. Check: `python workbench/tests/robustness_checks.py` (builds `dist/`, serves it with
`http.server`, checks preload progress, DPR 2 rendering, touch taps, pause when hidden, then the full
sandbox run). Frame-rate independence: `node --test runtime/test/framerate.test.mjs`.
