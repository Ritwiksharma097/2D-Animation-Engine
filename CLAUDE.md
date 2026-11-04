# Animation workbench: brief

You are building the first prototype of a 2D sprite **animation workbench** for a point-and-click game. Read `assets/reference/GPT_HANDOFF.md` once for history and `assets/manifest.json` for every asset's status and the owner's feedback.

## Why this exists

The owner kept having to point out obvious defects in generated sprite animation: feet sliding, frames that barely change or repeat, uneven motion, and the character's look drifting between frames and actions. The previous assistant's "checks" only verified that code ran and images fit their cells; nothing checked how the motion looked. The workbench's job is to **make motion problems visible and measurable**, so an AI assistant (which can read still images but cannot watch playback) can find defects before the owner does.

It does not fix bad drawings. It diagnoses them and makes good ones easier to use.

## Build, in this priority order

The cloud budget is limited and will run out, after which another assistant takes over on the owner's Windows PC. Commit and push after each step so finished work survives if the session stops.

0. **`FORMAT.md` and `PROGRESS.md` first.** `FORMAT.md` defines the JSON for an action (frame list, per-frame durations, loop mode, ground anchor, travel per frame) and for per-frame annotations (named contact points such as `foot_l`, `foot_r`, `hand_l`, with planted/free state), so ladders and ledges can be added later. `PROGRESS.md` is the handoff log: update it in every commit with what is done, what was visually verified and how, known problems, and the exact next step.
1. **Frame analysis library + CLI** (`workbench/analyze.py`, Python with Pillow, numpy, opencv-python-headless). For an action folder, report:
   - frame-to-frame change and its evenness; near-duplicate and out-of-order frames (a frame closer to a non-neighbour than to its neighbours), including the loop seam from last frame back to first
   - per-frame figure height, width, bounding box and baseline, plus the colour palette, with drift flagged against the character's `identity_reference`
   - for walks: stride width over time, contact vs passing poses, and a foot-contact estimate (lowest opaque pixel clusters). Then **foot slide**: given a travel speed per frame, how far a planted foot moves on the ground in game space. Also recommend the travel per frame that keeps the planted foot still.
   - Output `report.json` with a short plain-English summary. Every heuristic states its limits; flag only as "suspect", never "pass".
2. **Diagnostic images** the assistant can read instead of watching playback (PNG, written next to the report):
   - contact sheet with frame numbers
   - onion-skin overlay (frames tinted by time)
   - **world-space strip**: the character walking across a ground line at the given travel speed, with contact feet marked and a slide distance annotated
   - metric charts: change per frame, stride, height
   - side-by-side with the identity reference at the same scale
3. **Browser workbench** (`workbench/index.html`, static, vanilla JS, no build step; served with `python -m http.server`):
   - load any action from the manifest
   - play, pause, step, scrub; per-frame duration editing; loop and ping-pong
   - onion skin with adjustable range
   - in-place vs moving-across-ground preview with a visible baseline
   - click to set and edit foot-contact points per frame, saved as JSON in `annotations/<character>/<action>.json` (never inside `assets/`) and downloadable
   - show `report.json` flags beside the timeline, and compare two actions or characters side by side
4. **Annotations feed back in.** When a contact JSON exists, `analyze.py` uses it instead of the heuristic, and the moving preview derives travel from the planted foot so it cannot slide.
5. **Run it all on real data** and write `REPORT.md`: guard walk and guard idle (rejected), Ren 4-pose walk (approved), and the two rejected Ren walks. Embed the diagnostic images. The tool earns trust only if it flags the rejected walks and the guard walk for the problems the owner described in the manifest. Expect the approved Ren walk to score better, but don't tune thresholds to make it pass: if it measurably slides too, report that. Say plainly where it agreed with the owner, where it didn't, and why.

Out of scope for now: generating or redrawing art, rigs/Blender/Krita, game logic, ladders/ledges (design the data format so contact props can be added later).

## Rules

- `assets/` is source material. Never modify or overwrite files there; write outputs to `out/` (gitignored except `out/report_examples/` you choose to keep for REPORT.md).
- **Verify visually.** Install Playwright (Chromium), screenshot the workbench in the states you claim work, and actually look at the screenshots and diagnostic PNGs before reporting. Don't present code checks as visual verification.
- Be honest about limits. A heuristic that can't tell a good walk from a bad one is a finding to report, not something to hide.
- Everything must also run on Windows with Python 3.14: use `pathlib`, no shell-specific scripts, and pin nothing that lacks 3.14 wheels. If Playwright or another dependency can't be installed in the cloud, say so in `PROGRESS.md` rather than claiming verification.
- Keep code small and readable; add unit tests for the metric functions using synthetic frames (e.g. a drawn rectangle "foot" moving a known distance).
- Document how to run everything in `README.md`.

# Phase 2

Phase 1 (steps 0-5 above) is done and was checked on the owner's Windows PC (see `PROGRESS.md`). Same rules apply: commit and push after each step, keep `PROGRESS.md` current, verify visually, report honestly. Work in this priority order; stop cleanly wherever the budget runs out.

6. **Close phase 1's gaps.** Exercise with Playwright, and fix if broken: drag to move a contact, shift-click delete, ping-pong, per-frame durations actually changing playback speed. `analyze.py --all` should run every action in the manifest, not just five; any action it can't analyse should be skipped with a reason.
7. **Non-destructive edit layer.** Fixes to an action are stored in its `annotations/` document and applied by analysis, preview and export, never by touching `assets/`. They are:
   - frame order, holds (one drawing shown for several frames), dropped frames and per-frame durations
   - per-frame x/y offset, plus a "snap to ground" that puts the planted foot (or the lowest pixel, failing that) on `ground_y`
   - a mirror flag

   Add an **auto-suggest** for idles: group near-duplicate frames into held poses and propose a calmer timing. Apply it to the guard idle and his floating walk baseline, and show before/after diagnostics. Whether the result looks right is for the owner to judge, so give them a link or command to see it.
8. **Props and context for ledges and ladders.** In the workbench and the diagnostics, place a ledge (adjustable height and front edge) or a ladder (rails and rung spacing) in the scene. The action is drawn at an anchor that moves along a path (e.g. a straight line from floor to ledge top, as in the old demos). Hand and foot contacts can be marked as on a prop surface, and the tool flags a planted contact that isn't on any surface ("reaching into air", "pushing off nothing") or a body that intersects the prop. Note the cell size differs per action (`cell_size` in the manifest).
   - **Calibrate on `ren/climb_up` and `ren/climb_down`.** These are the climbs the owner called "perfect"; the manifest's `old_scene` gives the exact ledge and path they were played with. Rebuild that scene first, annotate the contacts, and report what the tool says. Like the approved walk: don't tune it to pass.
   - **Then judge the guard.** Run `guard/climb_up` and `guard/climb_down` (the owner couldn't judge them without a ledge) and `guard/ladder_up` (rejected) against the same kind of props. Find the ledge height and path that best fit his drawings, and report where contacts float or clip.
9. **Per-region identity check.** Replace the whole-figure palette check with regions (hood, hair, face, sash/tabard, armour), located from the identity reference or by a few clicks in the workbench. Compare colour and size per region across frames and actions. Test it on Ren's jump, which visibly differs from the walk although the owner accepted it, and on the rejected walks.
10. **Export for the game.** Write a packed sprite sheet plus JSON per action: frame rectangles, durations, the anchor, per-frame travel, contacts and props. Then make a small standalone playable page that uses only the exports: Ren walks on click (speed from contacts), climbs the ledge and jumps a gap. It should show that an exported walk doesn't slide. Use the Ren 4-pose walk with contact-derived travel, and state plainly that a 4-drawing walk will look choppy whatever the travel.
11. **More annotations.** Annotate contacts for the guard walk and Ren's rejected fourteen walk, and compare annotated with heuristic results in `REPORT.md`.

Out of scope: generating or redrawing art, rigs, the actual game.

# Phase 3

Phases 1-2 are done; see `PROGRESS.md` (including the owner-PC check of phase 2). Same rules: commit and push after each step, keep `PROGRESS.md` current, verify visually, report honestly, stop cleanly when the budget runs out.

12. **Correct the climb calibration.** Phase 2 tested Ren's climbs against a straight-line path, which was the brief's mistake: the old demo pinned his hand to the ledge pose by pose. The manifest's `old_scene` now describes the real path, and `annotations/ren/climb_*.json` `scene.path` holds its exact per-frame points (the straight line is kept as `path_straight_line_assumption`). With the real path, climb up shows feet on the floor in frames 1-7 and hands/knees on the ledge after that; remaining issues are a 6-9 game px sink in frames 12-13 and clip flags from fingers curling over the cap. Then:
    - Fix `ren/climb_down`: it still flags feet 124 px off the floor in frames 6-7 and feet labelled `ledge_top` in frames 13-14 that are on the floor. Check whether its contact labels are wrong or whether the down drawings really don't match the up table.
    - Reduce clip over-reporting where it is a drawing convention (fingers over the ledge corner, a near limb in front of the ledge face), and say what you allow and why.
    - Rewrite REPORT.md's climb section: withdraw the "perfect climb floats" finding and explain the cause.
    - Redo the guard climb fits with a contact-pinned path (`from_contacts` or per-pose points) rather than a straight line.
    - Playtest bug: clicking the floor near the ledge lets Ren walk into the ledge face; stop walking before solids.
13. **One climb, different ledge heights.** This is the owner's long-standing question. For a given ledge height, generate the climb path from the planted contacts (hands pinned on the ledge, feet on the floor, then knees/feet on the top). Sweep Ren's climb over roughly 60-140% of the original height and report the range where contacts stay on surfaces and the body doesn't visibly clip, with scene images at a few heights. In the playtest, add a ledge-height control that uses this, and visibly mark heights outside the supported range. State plainly that outside that range the drawings won't work: it needs new drawings or another climb category (step-up, pull-up).
14. **Redraw specs, not art.** For drawings that must be redone, produce a pose-target sheet whoever draws them can follow (Krita or image generation):
    - The guard walk: 8 frames (contact, down, passing, up, twice, with legs swapping), each with foot target positions on the ground line, stride and bob scaled from his height, over a faint silhouette of his current drawing, plus the measurable criteria a new set must pass in `analyze.py`.
    - Ren's 4-pose walk: the 4 in-betweens the owner asked for, with foot targets such that 8 frames at the old 41.9 px/frame don't slide.
    - Make it easy to check new frames: drop them in a folder, run one command, get the report against the spec.
15. **Owner review page.** One page (served by `serve.py`) listing every action with thumbnail, the owner's status and feedback, the tool's flags in plain English, links to the workbench view and diagnostic images, and before/after for edited actions. Let the owner record a verdict and comment per action, saved to `annotations/_reviews.json`. The owner should be able to review everything without running commands beyond starting the server. Add a `start_workbench.bat` that starts the server and opens this page on Windows.
16. **Playtest completeness.** Climb down, walking left (mirrored), jump timing in the export, Ren's idle while standing, and the guard patrolling on the same floor with his edited idle and walk at a consistent scale. Add a toggle that shows contact pins and drift.
17. **Identity regions by clicking in the page**, saved to `_identity.json`.

Out of scope: generating or redrawing art, rigs, the actual game.

# Phase 4

Phases 1-3 are done and were checked on the owner's Windows PC (see `PROGRESS.md`). Same rules: commit and push after each step, keep `PROGRESS.md` current, verify visually, report honestly, stop cleanly when the budget runs out. The owner's open decisions from phase 3 (guard ledge reading, Ren's 39 px step-in, 180 ms walk timing, commissioning new frames) are still open: don't decide them, but keep each easy to change in one place.

18. **Fixes from the owner-PC check.**
    - The review page fires about 60 HEAD/GET requests for optional files (`scene.png`, `before_after.png`, `ledge_100.png`, missing annotations) that 404 and fill the console with errors. Serve a file list from `serve.py` instead, and probe only what exists.
    - While `serve.py` is still preparing reports in the background (about a minute on first start), the review page shows actions without their before/after images and gives no hint. Show a "preparing N reports..." notice and refresh when they're ready.
    - Playtest: Ren and the guard start on the same spot, overlapping, so start them apart. The guard is drawn at Ren's scale, which is an assumption: add a per-character `game_scale` (or relative height) setting in one place, mark the guard's as unconfirmed, and show it on the review page so the owner can set it.
    - The playtest stage uses a small part of the page; let it fill the width.
19. **Art intake for the next art round.** New frames will come from image generation or Krita. Make one command take a generated sheet or a folder of frames and:
    - find the figures (grid or connected components, keeping detached effects and props, as `../gpt` build scripts did), scale them to the character's reference height, and align them on the ground and contacts
    - write an action into `incoming/<character>/<action>/` (never `assets/`) with its own registry file
    - run the analysis and, if a spec is named, `spec_check`
    - list it on the review page as "new, awaiting owner" with its report, beside the action it would replace

    Test it with synthetic sheets, and with an existing asset re-packed into a sheet; that round trip should reproduce the original frames within a pixel or two.
20. **A reusable animation runtime: the "engine" part.** Turn the playtest's ad hoc code into `runtime/` (vanilla JS module, no build step) that any game page can use.
    - Load exports.
    - A per-character state machine (idle, walk, turn, climb up/down, jump, one-shot reactions such as happy/eat/love, returning to idle).
    - Contact-driven travel, mirroring for facing, and the ledge-height adapter from step 13, refusing unsupported heights.
    - Events at named frames (e.g. "pickup" when the hand reaches the item), plus a debug overlay for contacts and drift.
    - Document its API in `runtime/README.md`, rebuild `play.html` on top of it, and add a small second demo for the guard: patrol, get distracted by food (eat), return to patrol. Unit-test the state machine and travel logic in Node if available, otherwise with Playwright.
21. **Ladders, end to end.** Rung contacts, a looping climb that adapts to ladder height by cycle count, getting on at the bottom and off at the top, and checks that hands and feet land on rungs. Run it on the guard's ladder and write a pose-target spec for a redrawn ladder cycle (the current one keeps the feet at one height), like step 14.
22. **Krita round trip.** Krita is installed on the owner's PC; there is none in the cloud. Export an action plus its spec as a PNG sequence with separate guide images (onion ghosts, foot targets, ground line) that Krita's animation import can load. Document the steps to draw in-betweens in Krita and bring them back through step 19's intake. If writing `.kra` files directly is reliable (Krita's format is a zip with XML), do that too, and say how far it was tested without Krita.

Out of scope: generating or redrawing art yourself, rigs, the actual game's story and levels.
