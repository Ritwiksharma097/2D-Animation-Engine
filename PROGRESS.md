# Progress log

Handoff log for the animation workbench. Update in every commit.

## Status

| Step | State |
| --- | --- |
| 0. FORMAT.md / PROGRESS.md | done |
| 1. analyze.py library + CLI | not started |
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

## Known problems

- none yet

## Next step

Write `workbench/analyze.py` (step 1).
