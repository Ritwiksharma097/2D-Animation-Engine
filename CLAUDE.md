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
