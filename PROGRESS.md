# Progress log

Handoff log for the animation workbench. Update in every commit.

## Status

| Step | State |
| --- | --- |
| 0. FORMAT.md / PROGRESS.md | done |
| 1. analyze.py library + CLI | done (11 unit tests pass) |
| 2. Diagnostic images | done |
| 3. Browser workbench | done (screenshots checked) |
| 4. Annotations feed back | done (Ren keypose annotated via the UI) |
| 5. Real-data REPORT.md | done |

## Environment notes (cloud session)

- Python 3.13 in the cloud container (target is 3.14 on Windows). Pillow, numpy,
  opencv-python-headless, pytest installed with pip. Python `playwright` installs; a Chromium build
  is pre-installed at `/opt/pw-browsers`.

## Visually verified

- Looked at contact sheets (made ad hoc) of guard/walk, ren/walk_keypose, ren/rejected_walk_fourteen
  and ren/rejected_walk_flatboy to understand the data. Observations: guard walk frames look very
  similar to each other with no obvious passing pose; Ren keypose 1 and 3 are both contact poses
  and look almost identical in silhouette (legs swap but side view hides which is which);
  flatboy frames have a smaller stride and a different face/proportions from the keypose walk.

## Step 1 notes (analyze.py)

- **Pose change** = 1 - IoU of opaque silhouettes at 1/4 resolution. A first version used per-pixel
  colour change, but every generated frame re-renders shading, so even near-identical guard idle
  poses differed by 5-26% and nothing read as a duplicate. Colour change inside the shared
  silhouette is kept as a separate "detail" metric (redrawn detail / boil).
- **Foot slide** without annotations is a *lower bound*: each step pairs whichever planted
  clusters would slide least. Recommended travel is searched in 0.4-1.6x of a stride-based estimate
  (2 x contact stride / steps per loop) because an unconstrained search returns 0 px/frame for
  drawings whose feet never move backward (guard walk, flatboy), which is itself flagged as
  `stance_not_moving`.
- **Steps per loop** = runs of frames below the stride midpoint (first try counted stride peaks; it
  found 4 peaks in a visibly 2-step walk because of plateaus).
- Thresholds are in `TH` at the top of analyze.py. They were set before looking at metric values,
  except the duplicate threshold (3% silhouette) which was picked after switching to silhouettes and
  seeing guard idle steps of 1-5%. Nothing was changed to make the approved walk pass.
- First real-data numbers (heuristic contacts, travel from manifest): guard walk 14 frames, no clear
  passing pose (narrowest stride 57% of widest), 3 steps per loop, feet don't move backward.
  Ren keypose: 2 steps, clear passing, but at the old 41.9 px/frame the planted foot would slide
  >=127 px per loop; stance motion implies ~69 px/frame. Palette histograms do not separate the
  walks (total variation ~0.1 for all); head-width ratio does (keypose 1.06x idle, fourteen 1.14x,
  flatboy 1.25x).

## Step 2 notes (diagnostics.py)

Writes next to report.json: `contact_sheet.png`, `onion.png`, `charts.png` (change per step,
height, baseline, proportions, stride with C/P marks, slide per step, slide-vs-travel curve, pose
distance heatmap), `identity.png` (reference beside sampled frames, guide lines at the reference's
top / 25% / baseline, palette shares), and for walks three world-space strips: at the given travel,
at the best constant travel, and at per-frame travel matched to the planted foot.

Visually checked (opened the PNGs and looked): guard walk contact sheet + charts + best-constant
strip, Ren keypose strip, fourteen strip, flatboy identity, guard idle onion. Fixes made after
looking: wrapped headers that were cut off, flag labels that overlapped, legends over titles,
clipped onion legend, and the guard strip which was an unreadable blur of 28 overlapping figures
(now the full figure is drawn every k frames, all frames in the 2x feet zoom).

What the images showed: guard idle outlines nearly coincide (barely moves); guard walk lowest
pixel sits 5-13px above the y=535 ground line and bobs; Ren keypose at 41.9 px/frame slides
20-43px per step (stance foot moves 61-85px per drawing); fourteen slides worst at the passing
frames (3->4, 10->11); flatboy's head is visibly larger than the idle reference.

## Step 3 notes (browser workbench)

`workbench/index.html` + `app.js` (vanilla JS). `workbench/serve.py` serves the repo and accepts
`PUT /annotations/<c>/<a>.json` and `POST /api/analyze`; with plain `python -m http.server` the page
still works and Save falls back to a download. URL hash parameters (`#a=guard/walk&b=...&mode=moving&
travel=41.9&steps=5&onion=3,3&frame=7&zoom=0.5`) set up a state, which the screenshot script uses.

Playwright (Python package `playwright`, Chromium pre-installed in the cloud box) works here.
`python workbench/tests/screenshot_workbench.py` writes `out/screenshots/*.png`. I opened and looked
at: guard walk in place with onion 3/3 (blue/orange halos visible, ground line, heuristic foot
squares, red flag dots on timeline, flags list), Ren keypose moving at 41.9 px/frame (character
moves along a ticked ground; red slide bar + readout "37.2 cell px" on step 1->2 matching the
report), and compare guard vs Ren side by side at the same zoom. Playback checked by reading the
frame index before/after 0.7 s (1 -> 9 at 83 ms/frame). Contact editing and Save are not yet
exercised by a screenshot (done in step 4).

Not visually verified: drag-to-move a contact, shift-click delete, ping-pong, per-frame duration
inputs changing playback speed (code paths exist; only the duration display was seen).

## Step 4 notes (annotations feed back)

- `analyze.py` reads `annotations/<c>/<a>.json`: frame order, durations, loop mode, ground y and
  travel (`constant`, `per_frame`, `from_contacts`). With annotated contacts, feet are matched by
  name, every shared planted contact must stay put (worst one counts, so it is no longer a lower
  bound), and `from_contacts` travel is the advance that keeps them fixed. Steps with no shared
  planted contact get the mean and a `no_shared_contact` flag. 3 new unit tests (14 total).
- `annotations/ren/walk_keypose.json` was made **through the UI** (Playwright clicking the canvas
  at points I read off a 2x zoom of the boots, then Save via serve.py, then "Re-run analysis").
  Points: the front boot's heel at heel-strike, the back boot's toe at push-off, heel and toe of the
  flat stance boot, so each step tracks the part of the boot that stays on the ground. They are my
  reading of the drawings, not the owner's.
- Result: stance travel per drawing is 98 / 70 / 108 / 81 cell px (mean 89). At the old demo's
  41.9 px/frame the annotated feet slide 189 cell px per loop (~90 game px at scale 0.4777); best
  constant travel 81 px/frame still leaves 55 px. With `from_contacts` travel, slide is 0.
- Visually verified in the browser (screenshots 06-08 in out/screenshots/, opened and looked at):
  editing frame 2 shows the three points and the table; moving preview with contact-derived travel
  shows planted-foot slide 0.0 px; with 41.9 px/frame it shows a red slide bar of 28.1 px on the
  toe_l step 2->3 (70 - 41.9), matching the report.

## Step 5 notes

REPORT.md compares tool findings with the owner's verdicts, with images in `out/report_examples/`
(committed; the rest of `out/` is gitignored). All embedded PNGs were opened and looked at.
Main findings: guard walk has no passing pose, 3 narrowings per loop, feet that never move backward
(slides at any speed) and floats 5-11px above y=535; guard idle is ~6 distinct poses (9 frames one
pose); both rejected Ren walks slide heavily and have larger heads than the idle; the approved
keypose walk is best on every measure except slide: at the old 41.9 px/frame it slides ~90 game px
per loop because the drawings imply ~89 px per drawing. Disagreements are listed in REPORT.md.

# Phase 2

| Step | State |
| --- | --- |
| 6. Close phase 1 gaps | done |
| 7. Non-destructive edit layer | done |
| 8. Ledge / ladder props | done (findings below; guard fits are heuristic) |
| 9. Per-region identity | done (seeded from the reference; no click UI) |
| 10. Game export + playable page | done |
| 11. More annotations | done |

## Step 6 notes

- `python workbench/tests/ui_checks.py` drives Chromium and **asserts** 9 things (9/9 pass in the
  cloud): drag moves a contact by exactly the mouse delta and adds no point; shift-click deletes the
  nearest point and the table updates; unsaved edits don't reach disk; ping-pong order
  1..14..2,1,2.. both by stepping and while playing; durations typed into the timeline drive
  playback (set 1000/83/400/83 ms, measured 1002/74/400/83 ms: the 74 is frame 1's overshoot carried
  into frame 2 at 60 fps refresh granularity). No bugs were found in these paths; nothing needed fixing.
- `analyze.py --all` now runs every action in the manifest (19; ~40 s with images). Each is checked
  first (folder exists, PNGs present, alpha channel, one frame size) and skipped with the reason if
  not; analysis exceptions are also caught and reported as skips. Currently 0 skipped.
  `--report-set` runs the five from REPORT.md.
- Per-action `cell_size` / `ground_y` from the manifest are now used by analysis and by the page
  (climbs are 512x448, ground 439.6). Screenshot `13_climb_up_cell512.png` checked.
- serve.py no longer logs every successful GET.

## Step 7 notes (edit layer)

- `workbench/edits.py` resolves order / hold / drop / durations / offset / snap-to-ground / mirror
  (FORMAT.md "Edits"); `analyze.load_action` uses it, so every report and image is of the edited
  action. `--no-annotations --tag original` writes the unedited analysis to
  `out/<c>/<a>__original/`; `diagnostics.before_after()` stacks the pair into `before_after.png`.
  New `timing.png` draws each played frame with width proportional to its time on screen.
  5 unit tests in `test_edits.py` (19 total pass).
- Page: per-frame dx / dy / hold / drop, action-level mirror and snap, "Suggest idle holds"
  (serve.py `POST /api/suggest-idle`), dropped entries shown dimmed, holds as "xN". `#...&b.raw=1`
  opens a viewer that ignores the document (the "before"). ui_checks.py now asserts 16 things
  (16/16 pass; re-run after step 11): drops leave playback, hold x duration drive it, raw viewer plays 14 frames, snap
  shift equals 535 - lowest pixel, mirror flips contact display, dragging on a mirrored frame
  edits source coordinates, mirrored travel runs along the new facing.
- Applied: `annotations/guard/idle.json` = auto-suggest (14 frames -> 6 held poses: 01, 02, 03,
  04 held x8 for 1.33 s, 12 x2, 14; cycle 1.17 s -> 2.67 s) + snap to ground.
  `annotations/guard/walk.json` = snap to ground only.
- Before/after, looked at: `out/report_examples/phase2/guard_idle_before_after.png` (timing strip,
  onion, contact sheet) and `guard_walk_before_after.png` (contact sheet, charts: lowest-pixel
  chart now flat on 535). After: guard idle loses uneven_jump/stall/overall and baseline_off but
  keeps near_duplicate / out_of_order (frames 2~4 and 4~6 are alike but not adjacent: the drawings
  wander back and forth) and few_distinct. Guard walk loses baseline_off/baseline_jitter; all walk
  problems (no passing pose, shuffling feet) remain, as expected: snapping can't fix the drawings.
- Judgement is the owner's. To see it: `python workbench/serve.py`, then
  http://localhost:8000/workbench/#a=guard/idle&b=guard/idle&b.raw=1&play=1 (left edited, right
  original, synced play) and the same with `guard/walk`.

## Step 8 notes (props and scenes)

- `workbench/props.py`: floor / ledge (front edge, height, cap) / ladder (rails, rung spacing)
  geometry, anchor paths (`line`, `points`, `vertical_loop`, `from_contacts`), checks and
  `scene.png` (one panel per frame over the props). `python workbench/props.py <c> <a>` uses the
  document's scene; `--path contacts` derives the path from planted contacts (`scene_contacts.png`);
  `--fit ledge` is a grid search (see failure below). Page: preview "scene" (drawn from serve.py's
  `POST /api/scene`, or the stored `scene_check.json` without the server), ledge height / front /
  rung spacing inputs that re-check live, and a surface picker for new contacts.
  `workbench/tests/scene_checks.py` screenshots 4 scenes and asserts a live edit (Ren ledge
  197 -> 260 px moves the frame-10 hand from 41.9 to 105.2 px off the top): PASS. Screenshots in
  `out/report_examples/phase2/2[1-4]_*.png` were looked at.
- **Calibration, Ren climb_up/climb_down (approved, "perfect").** Old scene rebuilt from the
  manifest (game px / 0.4777; cap thickness 8 game px assumed). climb_down is pixel-identical to
  climb_up reversed, so one set of contacts (mine, `annotations/ren/climb_*.json`) serves both.
  On the old straight path the tool flags the approved climb: feet drawn planted leave the floor
  by 16/31/47/62/77/91 cell px in frames 2-7 (8-44 game px), frames 3-4 touch nothing, and in
  frames 8-12 the planted hand / knee sit 12-46 px below the ledge top (body "clips" 9-45 px).
  Looked at `ren_climb_up_scene.png`: true, it is visible. Not tuned. Part of the clipping is the
  knee/shin overlapping the ledge front, which in a side view can read as the leg in front of the
  ledge, so `body_clips_prop` over-reports for side views.
  With the path derived from contacts (`ren_climb_up_scene_contacts.png`) the drawings fit the real
  197 px ledge reasonably: feet stay planted through frame 7 and hands land on the top in 8-12,
  but the reaching hand in 2-6 then goes 8-20 px into the ledge front, the knee in 10-11 is drawn
  36-46 px below the palm (can't both be on the top), and from frame 12 no contact is shared so x
  has to be pushed onto the ledge (+52 px jump for the hand at 9->10). My first annotation also had
  the trailing foot "planted" in 8-12; the implied ledge heights (17-72 px) showed it can't be, and
  it is now free.
- **Fitter calibration failed:** `--fit ledge` (cost = clipping + unsupported frames) picks a 32 px
  ledge for Ren instead of 197: lower is always "better" for that cost. Kept as a finding; it is
  not used for conclusions. What does encode height is a frame with a planted hand and foot.
- **Guard climb_up (unjudged).** Heuristic contacts (lowest foot cluster; front-most glove, which
  hits the moustache in 9, 10, 12, 13, so no hand there). Implied ledge height (foot y - hand y):
  222-243 px in the reach frames 1-4, 71-105 px when the hands come down in 6-8. Two readings,
  both with contact-derived paths: A = 230 px ledge grabbed during the reach: frame 5 contacts
  39.5 px off, clipping 22 px deep; B = 90 px ledge (~0.25 x his height), reach is a wind-up, hands
  on the top in 6-8: worst contact 9.5 px off, clipping 16 px in frame 6. B is stored
  (`annotations/guard/climb_up.json`, `guard_climb_up_scene.png`; A in `..._scene_A.png`).
  Either way his figure sinks 57 px inside the cell over the climb (lowest pixel 476 -> 533), so the
  frames are not floor-aligned; a fixed path can't fix that, contact-derived paths can.
- **Guard climb_down:** on the B ledge with a straight path (heuristic only): clipping up to 44 px
  (frames 3, 6, 8, 9) and frames 7, 10, 11 touch nothing. No contacts annotated.
- **Guard ladder_up (rejected):** ladder geometry is assumed (rungs 89 px, rails 160 px apart,
  2 rungs per loop). Robust part: his lowest foot stays at cell y 526-530 in all 14 frames, so the
  feet never step up relative to the body; at any climbing speed planted feet slide off the rungs
  (9-38 px here). The top-most-glove hand detector is unreliable (lands on the helmet in some
  frames), so hand results there are weak.

## Step 9 notes (per-region identity)

- `workbench/regions.py`: seeds in `annotations/<c>/_identity.json` (Ren: hood, hair, face,
  tunic, sleeves, satchel, trousers, boots; guard: helmet, armour, tabard, face, moustache, gloves;
  picked by me on a gridded view of each reference and colour-checked). `analyze.py` now flags
  `region_colour_drift` / `region_size_drift` / `region_missing` instead of the whole-figure
  palette flags. Region seeds are set by CLI (`regions.py seed`), **not by clicks in the page**
  (not built). 4 new tests (`test_props_regions.py`, 23 total pass). First version was
  inconsistent (reference vs itself gave 2.7x for the tunic); fixed so the reference scores 1.00x /
  dE 0 by construction.
- Results (`out/report_examples/phase2/ren_regions.png`, looked at; overlays land on the right
  parts, face only half covered because shaded skin falls outside the tolerance):
  approved walk: all regions dE 0.7-2.9, sizes 0.71-1.49x (pose: legs apart, satchel swings).
  **Ren jump** (accepted, "look differs"): colour shifted in nearly every region, hood 6.7, tunic
  6.8, hair 5.8, face 5.1, sleeves 5.2, boots 5.1 dE: agrees with the owner's note; it is a
  palette shift, not a size change. **Flatboy**: hair 1.51x, face 1.21x / dE 5.0, sleeves dE 8.9:
  agrees ("character changed"); hair stays under the 1.6x limit so only the sleeves are flagged.
  **Fourteen**: indistinguishable from the approved walk, again (same as phase 1).
  Ren climb (older style): face 0.32x / dE 9.7, sleeves dE 7.9: agrees with "identity differs".
  Guard (`guard_regions.png`): every sprite action's tabard is ~6-8 dE from the concept and smaller
  (0.13-0.55x); the concept art's blue differs from the sprites' or the sash band doesn't match the
  sprite pose. Weak evidence because the reference is concept art.

## Step 10 notes (export + playtest)

- `python workbench/export.py --demo` writes `out/export/ren/{walk_keypose,climb_up,jump}.{png,json}`
  (committed: `.gitignore` now keeps `out/export/`). `out/export/play.html` uses only those files:
  click floor = walk, ledge = walk to the climb start + climb (old approved straight path; ledge
  placed from the export's props, 94 game px high), far platform = walk to the edge + jump (arc in
  code over frames 4-9 plus the drawings' own lift) + walk. Open with `python workbench/serve.py`
  -> http://localhost:8000/out/export/play.html (needs http, not file://).
- Walk travel per drawing = 98/70/108/81 cell px from planted contacts; position changes only at
  frame changes. To get a sane speed I set the walk's durations to 180 ms in
  `annotations/ren/walk_keypose.json` (~240 game px/s); the owner should judge that.
  **A 4-drawing walk looks choppy whatever the travel** (stated on the page too).
- `workbench/tests/play_checks.py` (5/5 PASS): walk with contact travel has 0.00 game px planted
  drift; ticking "old constant 41.9" gives 31.6 game px drift; climb ends exactly on the ledge top;
  jump lands on the far platform; no page errors. Screenshots 30-33 looked at (in
  `out/report_examples/phase2/`).
- Not done: walking left uses the same frames mirrored in code (not an exported mirrored action);
  no climb_down in the demo; the jump's horizontal timing is hand-set in the page, not exported.

## Step 11 notes (more annotations)

- `annotations/guard/walk.json` (also keeps snap_to_ground) and
  `annotations/ren/rejected_walk_fourteen.json`: heel/toe contacts derived from each drawing (boot
  columns touching the drawn floor; heel if the touching run reaches the back 35% of the boot, toe
  if it reaches the front 35%), travel `from_contacts`. Labelling L/R: first attempt by nearest
  position swapped the legs at the passing frames (seen on the marked sheet); replaced by phase
  labelling for Ren (passing frames 4, 11). For the guard I saw that the same leg is in front in
  every drawing, so front = l throughout. The deriving script is not in the repo (it was a one-off
  in the session scratchpad); its rules are written here.
- Results and the heuristic vs annotated table are in REPORT.md "Phase 2 results". The heuristic
  under-reports slide by 1.5-2.6x but ranks the walks the same.
- Looked at: both annotated world strips (in `out/report_examples/phase2/`). Fixed the strip header,
  which said "least" for annotated contacts (it shows the worst shared contact).

# Phase 3

| Step | State |
| --- | --- |
| 12. Correct climb calibration | done |
| 13. One climb, different ledge heights | done |
| 14. Redraw specs | done |
| 15. Owner review page | done |
| 16. Playtest completeness | done |
| 17. Identity regions by clicking | done |

## Step 12 notes

- Ren climb_up on the real per-pose path: feet on the floor 1-7, hands/knees on the top 8-13
  (`out/report_examples/phase2/ren_climb_up_scene.png`, looked at). My phase-2 reaching-hand points
  were in the air ahead of the fingertips; now the front-most arm pixel, planted on the top in
  2-7 (they sit 3-10 px below the top edge, nearly constant x ~1021). Drawing 1's merged foot
  cluster renamed foot_r (the foot that stays). Remaining: frames 12-13 sink 12-18 cell px
  (6-9 game px), knee 15 px in front of the cap in frame 10, steps/re-grips between drawings.
- climb_down's phase-2 flags were my labelling bug (surface relabel keyed by climb_down's own file
  number; drawing k = climb_up drawing 15-k, verified pixel-identical). Contacts are now copied by
  drawing; it shows climb_up's results reversed.
- Clip allowances (props.py `HAND_ALLOW` 14 cell px around hand contacts, `FRONT_BAND` 40 cell px
  behind a ledge front below its top; hand contact tolerance 14 px). Reported as
  `allowed_overlap`; unit test updated (a 30 px sink through the top still clips).
- Guard climb_down annotated (heuristic: lowest foot on the top 1-4 then floor; glove planted on
  the top 1-7) on the 90 px ledge with a `from_contacts` path. `contact_path` gained two rules:
  ground contacts can't sit on the floor under a ledge (step in front of it), and frames with only
  floor contacts step clear of the face. Clean from frame 7; frames 3-6 (leg lowered over the
  edge) sink/clip and the hand/foot slide 24-45 px apart.
- Playtest: floor walks stop where the walk drawings' front-most pixel reaches the ledge face
  (+ the same 40 cell px front band). `play_checks.py` 6/6 PASS. Known: the walk stops ~39 game px
  short of the climb start (walk steps are ~40 px), so the climb begins with a jump forward.
- REPORT.md climb section rewritten: "perfect climb floats" withdrawn and the cause explained.

## Step 13 notes

- `workbench/ledge_sweep.py <c> <a>`: per height, `from_contacts` path + scene check, rows in
  `out/<c>/<a>/ledge_sweep.json`, images `ledge_<pct>.png`. Ren climb_up: strict 98-101%, looser
  (2x tolerance) 92-107%. Looked at 70% and 130%: frames 2-7 split the difference between feet
  on the floor and fingertips on the top (sink / float), frames 8-14 fine.
- `export.py` adds `paths_by_height` (60-140%, path, front_x, verdicts) and `height_rule` to
  `climb_up.json`. play.html: ledge-height slider (only while idle on the floor), ledge amber when
  marginal, red when unsupported, message says it needs new drawings or a step-up / pull-up.
- Fixed two playtest bugs found while testing: the climb started wherever the walk stopped (39 game
  px short of the climb start, so the hand pins missed the ledge); it now starts at the climb start
  (a visible 39 px step forward, recorded as `ren.popIn`). Walks could overshoot their target and
  never stop; the stop test is now directional.
- `play_checks.py` 9/9 PASS incl. 70% marked unsupported and climbing onto it, 100% marked
  supported. Screenshot 34 looked at.

## Step 14 notes

- `workbench/specs.py all` -> `specs/guard_walk.{json,png}`, `specs/ren_walk_inbetweens.{json,png}`
  (both sheets looked at). `workbench/spec_check.py <spec> <folder>` -> meets/MISSES per criterion,
  report + diagnostics in `out/spec_checks/<folder>/`. Test `test_specs.py`: synthetic frames
  drawn to the guard spec meet slide / steps / targets; 8 copies of one frame miss (24 tests pass).
- First version of spec_check wrote `spec_report.json` into the frames folder, which for the demo
  run was `assets/guard/walk/`; I deleted it immediately (git shows assets/ clean) and the report
  now always goes to `out/`. analyze.py's report paths no longer assume frames are inside the repo.
- Guard spec leaves out region colour/size criteria (concept-art reference differs from all his
  sprites). Ren spec: keys need non-destructive x offsets; exact slide-free travel is 44.6 px/frame;
  at 41.9 the residual is ~1.3 game px per frame.
- Ren's spec has not been run on real in-betweens (none exist yet).

## Step 15 notes

- `workbench/review.html` (http://localhost:8000/workbench/review.html): every manifest action
  with thumbnail, owner status + feedback, tool flags in plain English (details expandable),
  links to the workbench (plain, moving, scene, edited-vs-original), diagnostic images,
  before/after for edited actions, and a verdict + comment saved to `annotations/_reviews.json`.
  Filter: all / flagged / not reviewed / edited.
- `serve.py` now prepares reports in the background on start: any action whose report is missing
  or older than its annotations / `_identity.json` / the analysis code is re-analysed, and edited
  actions get the `__original` run + `before_after.png`, so a fresh checkout needs nothing but the
  server. Progress shows at the top of the page.
- `start_workbench.bat` (repo root): starts `serve.py` and opens the review page after 3 s.
  **Not run** (no Windows here); written by hand.
- `workbench/tests/review_checks.py` 6/6 PASS: 19 cards; deleted reports regenerated by the
  server; guard/idle shows before/after; verdict saves, survives reload. It restores
  `_reviews.json` afterwards (no test verdict left behind). Screenshots 40-41 looked at; that
  look is what found the stale climb_down report (old `palette_drift`), fixed by the staleness rule.

## Step 16 notes

- `export.py --demo` now also exports ren/climb_down (with `paths_by_height`), ren/idle,
  guard/idle (edited holds) and guard/walk (snapped; travel overridden to the stride-based
  21.9 cell px/frame because his contacts walk in place; scale assumed = Ren's 0.4777, recorded
  as `scale_source`). Ren's jump timing lives in `annotations/ren/jump.json` (`jump_timing`) and
  is exported as `jump` (air frames 5-7 = drawings lifted >15 px off the drawn floor; arc = their
  own lift, 102 cell px).
- `play.html` rewritten around one character model (draw/mirror/pins shared by Ren and the
  guard). `play_checks.py` 15/15 PASS (idle, both walk directions without drift, old timing
  slides, face stop, climb up, jump there and back, climb down, guard patrol + drift, toggle,
  70% ledge). Screenshots 30-37 looked at.
- Known: Ren's idle is one still drawing (as the manifest says); the jump's horizontal distance is
  set by the scene (gap), not by the drawings; climb start still jumps ~39 game px forward from
  where the walk has to stop.

## Step 17 notes

- `workbench/regions.html` (links in the workbench header and the review page): reference image
  cropped to the figure, seeds as coloured markers; select a row and click to move a seed, add a
  named region, delete, Save (`POST /api/identity`, validated names, writes `_identity.json` via
  regions.save_seeds and clears analyze's cached model), Check (`POST /api/regions_check`: table +
  overlay image for one action). `regions_checks.py` 5/5 PASS, restores the real seeds.
  Screenshots 50-51 looked at.
- Re-ran after step 17: 24 unit tests, ui_checks 16/16, scene_checks PASS (its live-edit number
  changed from 41.9 -> 105 to 1.5 -> 64.7 px because the climb now uses the real path and
  corrected hand points).

# Phase 4

| Step | State |
| --- | --- |
| 18. Owner-PC fixes | done |
| 19. Art intake | done |
| 20. Runtime ("engine") | done |
| 21. Ladders end to end | done |
| 22. Krita round trip | done (file level; Krita never run) |

Open owner decisions (not decided here; each lives in one place, listed in
`annotations/_settings.json` `open_decisions`): guard ledge reading, Ren's 39 px climb step-in,
180 ms walk timing, commissioning new frames.

## Step 18 notes

- `serve.py` `POST /api/inventory`: per action the files in `out/<c>/<a>/`, whether an annotation
  exists, whether it is edited, plus reviews, settings and background-preparation state. The
  review page loads optional files only if listed: **0 error responses** on load (was ~60 404s).
- Review page: yellow "Preparing N reports..." banner while the server prepares; cards being
  prepared say so; the page refreshes itself (before/after appears without a reload).
- `annotations/_settings.json` + `workbench/settings.py`: per-character `game_scale` with
  `confirmed`/`source`. The guard's is 0.4777, **unconfirmed** (assumed = Ren's). The review page
  shows both scales; saving one writes the file and re-exports the playtest in the background
  (~30 s). `export.py` reads scale from settings (no more hard-coded REN_SCALE).
- Playtest: Ren starts at x=70, the guard at 300; the canvas is now page-width; the page says the
  guard scale and whether it is unconfirmed.
- `workbench/tests/phase4_fixes_checks.py` 9/9 PASS (banner shown while preparing, before/after
  after preparation, no error responses, guard UNCONFIRMED, scale saves, re-export uses it,
  characters apart, stage width, no page errors). Restores `_settings.json` and the exports.
  Screenshots 60-62 looked at.

## Step 19 notes

- `workbench/intake.py <sheet|folder> --character C --action A [--replaces X] [--grid CxR] [--spec S]`:
  background keyed out from the border colour when there is no transparency; figures by grid or by
  connected components (pieces under 20% of the largest join the nearest figure, so detached effects
  and props stay; reading order rows then left-to-right); uniform scale to the replaced action's
  median height (or the identity reference); each frame placed like the assets: head centre (median
  x of the top third) at the target head x, lowest pixel on ground_y; writes `incoming/C/A/` +
  `intake.json`; analyses (as a walk if it replaces one) and runs spec_check into `out/incoming/`.
  With a spec that has `head_x`, the head is aligned to the spec (the guard spec now records 318).
- Round trip: ren/rejected_walk_fourteen re-packed into a 7x2 sheet (cropped, re-spaced) came
  back with every frame within +-1 px of its original position (5 of 14 identical) via the grid; via
  a white-background sheet and connected components also +-1 px, but soft edges are lost (blended
  into white, so ~4% of edge alpha differs). The +-1 px are the original assets' own alignment
  rounding.
- Synthetic guard sheet drawn to the spec, shrunk to 60%, irregular spacing, white background:
  8 figures found, rescaled to his height, analysed as a walk: recommended travel 37.0 px/frame (the
  spec's 37.2), slide ~2 px per loop. Spec check misses only "distinct poses" (the rectangle drawing's
  two contact poses are identical silhouettes), as expected.
- Review page: intakes appear as "NEW, awaiting owner" cards right after the action they would
  replace, with spec result and images; filter "new, awaiting owner". `intake_review_checks.py`
  3/3 PASS; screenshot 63 looked at. Demo intakes were removed afterwards (no synthetic art left
  in `incoming/`). 2 new unit tests (`test_intake.py`, 26 total).
- Limits: background keying is a hard colour threshold with a soft ramp, not real matting; a figure
  touching another merges into one; contacts are not used for alignment yet (heads/ground only).

## Step 20 notes

- `runtime/anim.js` + `runtime/README.md` (API). Clips, World (floor + platforms, walk limits that
  stop before faces), Character (queue of walk/turn/climb up/down/jump/play/wait, back to idle;
  contact-driven travel; mirroring; ledge adapter that refuses heights outside the looser range;
  named frame events; debug overlay with pins and drift). `node --test runtime/test`: 7/7 pass
  (Node 22). Two test-data mistakes on the way (a walk with one foot planted all loop) were mine.
- `out/export/play.html` rebuilt on the runtime; `play_checks.py` 16/16 PASS. Behaviour change:
  at 70% the climb is now **refused** (the brief's "refusing unsupported heights"); 95% (marginal)
  climbs. `out/export/guard_demo.html`: patrol, click to drop an apple, he turns, walks so his hand
  meets the drawn apple (offset from the eating action's `pickup` point), eats, the prop vanishes on
  `pickup`, "nom" on `bite`, then patrols again. `guard_demo_checks.py` 5/5 PASS; screenshot 70
  looked at (mirrored, reaching the apple).
- Events added in annotations: guard/eating `pickup` (drawing 4) + `bite` (7) (+ snap_to_ground
  so he stands on the same floor as his snapped idle/walk; one flag to remove), ren/jump
  `takeoff`/`land`, ren/climb_up `hands_on_ledge`/`on_top`. The `pickup` point is from drawing 02
  before the snap shift (a few px).
- No turn drawings exist: `turn` is a 120 ms hold then a mirror.

## Step 21 notes

- `workbench/ladder.py`: `contact_rise` (planted ladder_rung contacts moving down the cell = body
  rise), `plan` (cycles for a ladder height, two rungs per cycle), `check` (scene with the spec's rung
  spacing, rails centred on his contacts, vertical_loop path; writes `out/<c>/<a>/ladder.{json,png}`),
  `spec` (`specs/guard_ladder.{json,png}`: 8 frames, diagonal limbs, grippers move down 16.8 px per
  frame). Both images looked at.
- Guard: contact rise 0 px/cycle (his annotation marks hand and foot planted in every frame, and his
  feet move 4 px), so the rise is assumed (2 x 67 = 135 px/cycle) and 53/56 frames have contacts off
  rungs. Phase 2's rails were centred on his feet, so his hands fell outside them; recentred.
- Export: `ladder` block (per-frame rise, `rise_assumed`, rung spacing, rungs per cycle). Runtime:
  `World.ladders`, `Character.climbLadder(id)` (walk to ladder, get-on cut, whole cycles, get-off cut
  onto `toSurface`), `rungError`; events `ladder_on` (cycles, assumedRise) / `ladder_off`. Node test
  8/8 (`node --test runtime/test/runtime.test.mjs`; a bare directory argument doesn't work in
  Node 22). Guard demo gained a ladder to a loft; `guard_demo_checks.py` 7/7 PASS, screenshot 71
  looked at.
- Not done: get-on / get-off drawings (none exist; both are cuts), ladder down (the old "down" was the
  up sequence reversed; the runtime has no `ladder_down` yet).

## Step 22 notes

- `workbench/krita_export.py <c> <a> [--spec S]` -> `out/krita/<c>_<a>/` with `frames/` (kept
  drawings, keys shifted by the spec's key offsets, blank cells to draw), `targets/`, `onion/`
  (previous blue / next orange), `ghost/` (current drawing named by the spec), `ground.png`,
  `pack.json`, `KRITA_STEPS.md`. Ren in-betweens: draw 2, 4, 6, 8; guard walk: draw all 8 over ghosts.
  Composited layers looked at (`out/report_examples/phase4/krita_layers_ren.png`): onion + targets
  sit on the ground line beside the kept keys.
- `intake.py --as-is`: frames already on the cell are copied untouched (no re-scale, no re-align);
  refuses frames of another size. `test_krita.py`: pack layout, simulated drawing saved with Krita's
  render names (`frame_0000.png`), intake --as-is -> pixel-identical (27 tests pass).
- **No `.kra` writer**: see `KRITA.md` (animated paint layers use Krita's undocumented tiled LZF
  format; not verifiable without Krita). Krita itself was never run here, so the import / render steps
  in KRITA_STEPS.md are from Krita's documented menus and untested.

# Phase 5

| Step | State |
| --- | --- |
| 23. Owner-PC fixes + new Ren reactions | done |
| 24. Levels and navigation | done |
| 25. Interactions and guard AI | done (logic tested in Node; seen in the sandbox, step 26) |
| 26. Mechanics sandbox | done |
| 27. Robustness and packaging | done |
| 28. ENGINE.md | done |

## Step 23 notes

- `_settings.json` `travel_overrides` (per action, cell px/frame, `confirmed`, `reason`);
  `settings.travel_override()`; `export.py` applies it and records `travel_override` in the export
  (the hard-coded stride-based guard speed in phase 4 is gone). Guard walk: 37.21 (his spec's
  travel), unconfirmed; listed under `open_decisions`. In the cloud the guard demo walked him at
  125 px/s before this change, so I could not reproduce the owner's 20 s; likely an export without
  the override. Runtime: `overrideSliding` + red "travel override: feet slide N px" label in
  `drawDebug`; Node test 9/9.
- Six Ren reactions analysed (`analyze.py --all`: 25 actions, 0 skipped) and region-checked;
  REPORT.md section written after looking at the region overlay, the identity sheets of happy,
  caught_game_over, ladder_up and the interact contact sheet.
- `annotations/ren/interact.json`: `hand_r` per drawing 3-8 (lowest skin pixel of the front hand),
  planted on the ground in 5-6; `pickup` event at drawing 5 (exported as frame index 4, with the point).

## Step 24 notes

- Level format in FORMAT.md; `levels/demo.json` (2600 px wide). `runtime/level.js`: `compileLevel`
  (walk regions split by ledges, face/edge sides), `worldFromLevel`, `surfaceAt`, `navGraph`
  (climbs on both faces via the ledge adapter, jumps by `jump_max_gap` / `jump_max_rise`, ladders
  only with a ladder clip that has rung data, no ladder-down), `planRoute` (Dijkstra over transition
  endpoints, only ok edges; when no route, lists the refused transitions), `queueRoute`, `goTo`,
  `Camera` (dead zone, frame-rate-independent easing, clamped). Runtime World gained floor regions,
  platform `base`, back-side (mirrored) climbs, `climbEndX`, ladders from any surface.
- `node --test runtime/test/level.test.mjs` 6/6 (one bug found by it: a ledge followed by another
  ledge got no back side), runtime tests 9/9.
- `out/export/level_play.html`: click anywhere, Ren routes there; camera follows; transitions drawn
  green / amber / red. `workbench/level_editor.html`: drag / resize props, numeric fields, add / delete,
  character select, transitions coloured and listed with reasons, save via serve.py.
  `level_checks.py` 8/8 PASS (onto the ledge, down its back, jump with the camera following, ladder
  platform and 170 px wall refused for Ren with reasons, dragging L1 80 px higher turns its climbs
  red, save). Screenshots 80-83 looked at.
- Limits: jumps are only between surfaces at nearly the same height (Ren's drawings are a same-level
  jump); the planner's walking cost ignores time spent in climbs; the editor doesn't snap or check
  overlaps.

## Step 25 notes

- `runtime/behaviour.js` (API in runtime/README.md): vision cone + line of sight, `decideGuard`
  (patrol / suspicious / chase / caught / distracted / eating / lovestruck hook), `GuardBrain`,
  `decideIdleHint`, `Inventory`, `Interactions` (take at the clip's event point, drop, throw), all
  configured by plain JSON. `node --test runtime/test/behaviour.test.mjs` 7/7. One bug caught while
  writing: finishing eating must clear the food or he is distracted by it again.
- Exports added for behaviour: ren interact (pickup event), caught_game_over, look_around,
  hurt_stumble, happy (all **unreviewed** art), guard angry, love, happy.
- The guard has no look-around drawing; "suspicious" alternates his facing.

## Step 26 notes

- `sandbox/index.html` + `sandbox/tuning.json` (every number: level, cover, hotspots, exit, throw,
  guard patrol / vision / suspicion / food / catch, idle hint, retry delay). One screen of
  placeholder shapes, existing art only. Ren: click to walk / climb (planner), click the apple to take
  it (interact pickup event), "throw apple" + click to land it; the bush blocks the guard's sight;
  the guard walks to food and eats; take the key on the ledge, leave through the exit behind it.
  Caught: Ren plays caught_game_over, guard angry, Retry. HUD: each character's clip with
  "NOT OWNER-APPROVED (status)" in red, guard mode / suspicion / sight reason, inventory.
- `sandbox_checks.py` 10/10 PASS: caught + retry; apple taken; in cover; the bush blocks sight
  (forced check: guard facing Ren within range -> "blocked bush"); thrown apple -> eating; key taken
  on the ledge; won; no page errors. Screenshots 90-93 looked at.
- Bug found by it: chase re-issued the walk every frame, which restarted the walk clip at frame 0
  so the guard never moved. Now it re-targets only when Ren moves > 30 px (`retarget_px`); Node
  test added (behaviour 8/8).
- Limits: the guard can't climb (his climb exports aren't used), so a chase stops at the ledge face;
  vision is a 2D cone from his eye to Ren's mid-body, so very close below his eye line reads
  "outside the cone"; the guard walk is the rejected one at the placeholder speed (its feet slide).

## Step 27 notes

- Runtime (`runtime/anim.js`): `loadClips(base, keys, onProgress)` reports `(done, total, key)`;
  `fitCanvas(canvas, w, h)` sizes the backing store to CSS width x devicePixelRatio and returns
  `reset(ctx)` (logical-px transform) and `toLogical(clientX, clientY)`; `run()` now steps the
  simulation at a fixed 1/240 s (`makeStepper`, frame time capped at 250 ms) and pauses on
  `visibilitychange` when the document is hidden (no catch-up jump on return).
- Sandbox uses all of it: a progress bar while clips load, `pointerup` input (mouse, pen, touch;
  `touch-action: manipulation`), drawing in logical 1200x520 at any DPR, refit on resize.
- `runtime/test/framerate.test.mjs`: walk + jump + guard decisions simulated at 30, 60 and 144 Hz
  give identical positions at every 1 s sample (Node 22, pass). All Node tests 24/24.
- `workbench/build_dist.py` -> `dist/` (44 files, ~26 MB, gitignored); refuses to build into source
  folders. `robustness_checks.py` 20/20 PASS against `dist/` served by plain `http.server`: progress
  reached 13/13 and hid; canvas 1748 backing px for 874 CSS px at DPR 2; a touch tap walked Ren;
  hidden -> positions frozen for 1.2 s, visible -> resumed; dist index + play / guard_demo /
  level_play load with no errors or 404s; full sandbox run 10/10. Screenshot 94 looked at (sprites
  sharp at DPR 2; my first version left the progress row visible because `.row{display:flex}`
  overrode `hidden`; the check now tests real visibility).
- `play_checks.py` "guard patrols" had started failing after step 23's faster placeholder speed: two
  samples 9 s apart landed on the same patrol end. He does patrol (x 33..407); the check now samples
  the range. Not a runtime change.
- Limits: only the sandbox uses `fitCanvas` and pointer input; play.html, guard_demo.html and
  level_play.html still draw at their fixed canvas size (scaled by CSS) and use click events. Touch
  was tested with Playwright's emulated touchscreen, not a real phone. The pause test fakes
  `document.hidden`; a real tab switch was not tried.

## Step 28 notes

- `ENGINE.md`: architecture and data flow (assets -> annotations/edits -> analysis -> export ->
  runtime -> levels -> pages / dist), how to add a character, an action and a level, a table of where
  each owner decision lives, what was verified on the owner's PC (phases 1-4) and what wasn't
  (all of phase 5, the Krita menu steps, real devices), and known limits. Checked its paths and
  commands against the code and the step notes; it adds no new behaviour.

## Known problems

- `proportion_bulk` (area / height^2 vs idle) is flagged on every walk including the approved one,
  because spread legs and swinging arms change it. Weak evidence; compare walks to each other.
- Palette metric does not catch colour changes (looked at the fourteen identity sheet: colours look
  the same to me too; hood shape differs, which the metric cannot see).
- Heuristic travel search is clamped to 0.4-1.6x a stride estimate; for walk-in-place drawings the
  "best" value is just the clamp edge.
- Playwright: the pip package wants a newer Chromium build than the one pre-installed in the cloud box;
  `screenshot_workbench.launch()` falls back to `/opt/pw-browsers/chromium-*`. On Windows, run
  `python -m playwright install chromium` once.
- Not verified: drag/shift-click contact editing, ping-pong playback, per-frame durations changing
  playback (display only). Nothing has been run on Windows or Python 3.14 yet.

## Checked on the owner's Windows PC (local assistant, 2026-11-04)

- Windows 11, Python 3.14.3: `python -m pytest workbench/tests` gives 14 passed. `python workbench/analyze.py --all` runs in about 9 s and its summaries match REPORT.md.
- Opened `out/guard/walk/charts.png` and the annotated keypose strip at 41.9 px/frame; both are readable and agree with the report.
- `python workbench/serve.py` + `#a=ren/walk_keypose&mode=moving&travel=41.9` loads with no console errors and shows the moving preview with contact markers.
- Not checked locally: drag/shift-click editing, ping-pong, duration editing (now phase 2 step 6).
- Added `ren/climb_up` and `ren/climb_down` (the liked grounded ledge climb, 512 x 448 cells, with the old scene geometry in the manifest) for phase 2.

## Phase 2 checked on the owner's Windows PC (local assistant, 2026-11-04)

- Python 3.14.3: 23 tests pass; `analyze.py --all` analyses 19 actions, 0 skipped. `assets/` unchanged by phase 2.
- **Correction to phase 2's climb finding.** The brief said the old demo moved Ren in a straight line; it didn't. `terra_demo/index.html` pins his hand to the ledge per pose. The real per-frame points are now in `annotations/ren/climb_*.json` (`scene.path`, type `points`), and the manifest's `old_scene` is corrected. With them, `props.py ren climb_up` shows feet on the floor in frames 1-7 and hands/knees on the ledge after that (looked at `out/ren/climb_up/scene.png`); remaining: a 6-9 game px sink in frames 12-13, and clip flags from fingers curling over the cap. `climb_down` still has flags (see phase 3, step 12).
- Re-ran `export.py --demo` so `play.html` uses the real path. Playtest checked in the browser: walk, then climb onto the ledge, no console errors. Bug: clicking the floor near the ledge lets Ren walk into the ledge face.
- Not rechecked locally: the guard idle edit, the Playwright UI scripts.

## Phase 3 checked on the owner's Windows PC (local assistant, 2026-11-04)

- Python 3.14.3: 24 tests pass. `assets/` unchanged by phase 3.
- `start_workbench.bat` works when run as a double-click would (Start-Process): the server starts, the review page opens in the default browser, and `review.html` returns 200.
- Review page lists every action with flags and links. The console shows ~60 404 errors from probing optional files, and the before/after images only appear about a minute after the first start, with no notice (phase 4, step 18). Looked at `out/guard/idle/before_after.png`: 14 frames at 83 ms became 6 held poses (2.67 s) with the feet on the ground line.
- Playtest loads with no console errors and the height slider shows 98-101% supported. Ren and the guard start overlapping, and the guard is at Ren's height (an assumption).

## Phase 4 checked on the owner's Windows PC (local assistant, 2026-11-04)

- Python 3.14.3: 27 tests pass. Node 24: `node --test runtime/test/runtime.test.mjs` gives 8 passed. `assets/` unchanged by phase 4.
- Guard demo in the browser, no console errors. Dropped an apple: he walks to it, the floor apple disappears at pickup, and he eats it with "nom". His walk is very slow (about 20 s for a third of the screen), the honest result of contact-derived travel on his walk-in-place drawings (phase 5, step 23).
- Krita 5.2.11 is installed. `krita_export.py ren walk_keypose --spec ...` builds the pack. A headless check via `kritarunner -s <module> -f main` did not run the script, either from the current folder or from `%APPDATA%/krita/pykrita` (no output, no error), so the Krita menu steps are still untested. The temporary script was removed.
- Imported six first-pass Ren reactions (`happy`, `interact`, `hurt_stumble`, `caught_game_over`, `look_around`, `ladder_up`) from `sprite_rework/sheets`, status "unreviewed". `analyze.py --all` now analyses 25 actions, 0 skipped.

## Phase 5 checked on the owner's Windows PC (local assistant, 2026-11-04)

- Python 3.14.3: 27 tests pass. Node 24: behaviour 6, framerate 1, level 9 and runtime 8 tests pass. `assets/` unchanged by phase 5.
- Played the sandbox in the browser (served by `serve.py`), no console errors. Picked up the apple and threw it; the guard walked to it and ate; Ren passed behind the bush (drawn translucent), climbed the ledge, took the key, was spotted climbing down (cone red, chase), and still reached the exit ("got out with the key!", retry button).
  Issues: the guard walked through Ren, who was standing behind him, without noticing, and the characters overlap. Being spotted while escaping did not lead to a catch (phase 6, step 29).
- `build_dist.py` on Windows writes 44 files (25.8 MB). Served `dist/` with `python -m http.server`: every file loads with 200. Once, while the browser window wasn't being drawn, the sandbox stayed at "loading animations 0/13" (`img.decode()` never resolved); after a reload it loaded and ran.

## Next step

Phase 5 is done (steps 23-28). Next, on the owner's Windows PC:
1. `git pull`, `python -m pytest workbench/tests`, `node --test runtime/test/runtime.test.mjs`
   (and `level`, `behaviour`, `framerate` test files), then `start_workbench.bat`.
2. Open http://localhost:8000/sandbox/index.html and play it once (caught, apple, cover, climb, key,
   exit); try `workbench/level_editor.html`; look at the guard demo's red slide note.
3. `python workbench/build_dist.py` and `python -m http.server -d dist 8080`; open the sandbox there.
4. Owner decisions still open: see ENGINE.md section 3.

Phase 4 follow-ups (older list):
1. On Windows: `start_workbench.bat`; run `phase4_fixes_checks.py`, `intake_review_checks.py`,
   `guard_demo_checks.py`, `play_checks.py`, `node --test runtime/test/runtime.test.mjs`.
2. Try the Krita round trip once in Krita (KRITA.md) with the Ren in-betweens pack; fix the steps
   if a menu differs.
3. Owner decisions, still open (each in one place, see `annotations/_settings.json`): guard scale,
   guard ledge reading, Ren's 39 px step-in, 180 ms walk timing, new frames.

Phase 3 follow-ups (older list):
1. On Windows: double-click `start_workbench.bat` (never run here) and review every action;
   `python workbench/tests/play_checks.py`, `review_checks.py`, `regions_checks.py`, `ui_checks.py`.
2. Owner decisions: guard climb reading (90 px ledge), whether the 39 px step-in before Ren's climb
   is acceptable or the walk needs a narrower stopping pose, and the walk speed (180 ms/drawing).
3. Commission new frames from `specs/guard_walk.png` and `specs/ren_walk_inbetweens.png`; check
   them with `spec_check.py`.
4. Other ledge heights need new reach drawings or a step-up / pull-up category (step 13).

Phase 2 follow-ups (older list):
1. On Windows: `python -m pytest workbench/tests`, `python workbench/tests/ui_checks.py`,
   `scene_checks.py`, `play_checks.py`; then look at the guard idle before/after and play.html with the owner.
2. Ask the owner which guard climb reading is intended (90 px ledge vs 230 px reach) and about
   the old Ren climb path (the tool says the feet float in frames 2-7).
3. Click-to-seed identity regions in the page (not built); a face-specific check (shape, not colour).
4. Export climb_down and a mirrored walk; move the jump's timing into the export.

Phase 1 follow-ups (older list):
1. On the Windows PC: `pip install -r requirements.txt`, `python -m pytest workbench/tests`,
   `python workbench/analyze.py --all`, `python workbench/serve.py`, and check the page by hand
   (especially drag editing and ping-pong, which are unverified).
2. Show the owner the keypose moving preview at 41.9 vs contact-derived travel (REPORT.md section).
3. Annotate the guard walk and one rejected Ren walk, so heuristic and annotated results can be
   compared on more than one action.
4. Replace the whole-figure palette metric with per-region colour (hood / hair / sash) to catch
   costume drift.
