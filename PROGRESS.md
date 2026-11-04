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
| 5. Real-data REPORT.md | not started |

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

## Known problems

- `proportion_bulk` (area / height^2 vs idle) is flagged on every walk including the approved one,
  because spread legs and swinging arms change it. Weak evidence; compare walks to each other.
- Palette metric does not catch the colour changes the owner described (not yet visually checked
  whether colours actually differ).

## Next step

Step 5: run `python workbench/analyze.py --all`, copy chosen PNGs to `out/report_examples/`, and
write REPORT.md comparing tool findings with the owner's verdicts.
