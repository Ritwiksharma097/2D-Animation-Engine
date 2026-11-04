# Art request 1: guard / walk

**What:** A new 8-drawing patrol walk: contact, down, passing, up, then the same with the legs swapped.

**Why it is ranked 1 (what it blocks in the sandbox):** He patrols on every screen. His walk is rejected, walks in place, and at the placeholder speed (annotations/_settings.json) his feet slide; the HUD shows it in red.

**Now:** `guard/walk` is *rejected*. Owner: "Same problem as idle. Frames repeat similar steps; no clear passing pose; first priority to diagnose." See `current.png`.

## Files

- `identity/reference.png`: the identity reference figure (`guard/concept.png`).
- `identity/regions.png`: the identity regions the tool checks (helmet, armour, tabard, face, moustache, gloves), each at full strength with its reference colour.
- `identity/approved_poses.png`: the owner-approved drawings at one scale (6 frames). Match these.
- `spec_sheet.png`: the pose-target sheet (foot targets on the ground line over a faint silhouette).
- `spec.json`: the criteria `spec_check.py` measures (`specs/guard_walk.json`).
- `prompt.txt`: an image-generation prompt template.
- `current.png`: the drawings this replaces (contact sheet with the tool's flags).

## Checklist

Measured by the intake command below (`spec_check.py`):

- `frame_count`: 8
- `distinct_poses`: 8
- `near_duplicates`: 0
- `steps_per_loop`: 2
- `max_min_stride_ratio`: 0.45
- `max_pose_change_cv`: 0.35
- `travel_px_per_frame`: 37.21
- `max_slide_per_loop_px`: 29.8
- `baseline_tolerance_px`: 3
- `ground_y`: 535.0
- `planted_target_tolerance_px`: 17.9
- `no_flags`: ["stance_not_moving", "slide_unavoidable", "out_of_order"]

Checked by eye (the tool cannot):

- [ ] legs visibly swap between frames 1 and 5 (the tool cannot tell left from right)
- [ ] same costume, proportions and colours as the approved poses (region check helps but does not see shapes)
- note: Region colour/size checks are left out for the guard: his only reference is concept art whose tabard differs from every sprite; compare with his approved actions by eye.

## After drawing

Run (from the repository root; the result goes to `incoming/`, never `assets/`, and shows on the review page as "new, awaiting owner"):

```
python workbench/intake.py <your_sheet_or_folder> --character guard --action walk_v2 --replaces walk --spec specs/guard_walk.json
```

"Meets" means the measurable criteria hold; it is not a judgement of how it looks. The owner decides.
