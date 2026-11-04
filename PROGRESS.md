# Progress log

Handoff log for the animation workbench. Update in every commit.

## Status

| Step | State |
| --- | --- |
| 0. FORMAT.md / PROGRESS.md | done |
| 1. analyze.py library + CLI | done (11 unit tests pass) |
| 2. Diagnostic images | not started |
| 3. Browser workbench | not started |
| 4. Annotations feed back | not started |
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

## Known problems

- `proportion_bulk` (area / height^2 vs idle) is flagged on every walk including the approved one,
  because spread legs and swinging arms change it. Weak evidence; compare walks to each other.
- Palette metric does not catch the colour changes the owner described (not yet visually checked
  whether colours actually differ).

## Next step

Step 2: `workbench/diagnostics.py` writing contact sheet, onion skin, world-space strip,
metric charts and identity side-by-side next to report.json.
