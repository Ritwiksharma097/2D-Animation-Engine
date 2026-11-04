# Animation workbench: brief

You are building the first prototype of a 2D sprite **animation workbench** for a point-and-click game. Read `assets/reference/GPT_HANDOFF.md` once for history and `assets/manifest.json` for every asset's status and the owner's feedback.

## Why this exists

The owner kept having to point out obvious defects in generated sprite animation: feet sliding, frames that barely change or repeat, uneven motion, and the character's look drifting between frames and actions. The previous assistant's "checks" only verified that code ran and images fit their cells; nothing checked how the motion looked. The workbench's job is to **make motion problems visible and measurable**, so an AI assistant (which can read still images but cannot watch playback) can find defects before the owner does.

It does not fix bad drawings. It diagnoses them and makes good ones easier to use.

## Build, in this priority order

The cloud budget is limited. Commit and push after each step so finished work survives if the session stops.

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
   - click to set and edit foot-contact points per frame, saved as JSON next to the frames and downloadable
   - show `report.json` flags beside the timeline, and compare two actions or characters side by side
4. **Annotations feed back in.** When a contact JSON exists, `analyze.py` uses it instead of the heuristic, and the moving preview derives travel from the planted foot so it cannot slide.
5. **Run it all on real data** and write `REPORT.md`: guard walk and guard idle (rejected), Ren 4-pose walk (approved), and the two rejected Ren walks. Embed the diagnostic images. The tool earns trust only if it flags the rejected walks and the guard walk for the problems the owner described in the manifest, and doesn't heavily flag the approved Ren walk. Say plainly where it agreed with the owner, where it didn't, and why.

Out of scope for now: generating or redrawing art, rigs/Blender/Krita, game logic, ladders/ledges (design the data format so contact props can be added later).

## Rules

- `assets/` is source material. Never modify or overwrite files there; write outputs to `out/` (gitignored except `out/report_examples/` you choose to keep for REPORT.md).
- **Verify visually.** Install Playwright (Chromium), screenshot the workbench in the states you claim work, and actually look at the screenshots and diagnostic PNGs before reporting. Don't present code checks as visual verification.
- Be honest about limits. A heuristic that can't tell a good walk from a bad one is a finding to report, not something to hide.
- Keep code small and readable; add unit tests for the metric functions using synthetic frames (e.g. a drawn rectangle "foot" moving a known distance).
- Document how to run everything in `README.md`.
