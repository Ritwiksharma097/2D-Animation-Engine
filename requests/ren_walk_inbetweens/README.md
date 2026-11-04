# Art request 3: ren / walk_keypose

**What:** The 4 in-betweens the owner asked for, between the 4 approved key poses (8 frames: key, in-between, key, ...). Keep the keys' look exactly.

**Why it is ranked 3 (what it blocks in the sandbox):** Ren's walk is approved but has 4 drawings, so every walk in the sandbox looks choppy whatever the travel. It is the most-seen animation.

**Now:** `ren/walk_keypose` is *approved*. Owner: "Liked. Owner wants extra in-between frames for smoothness without losing identity or the poses." See `current.png`.

## Files

- `identity/reference.png`: the identity reference figure (`ren/idle/01.png`).
- `identity/regions.png`: the identity regions the tool checks (hood, hair, face, tunic, sleeves, satchel, trousers, boots), each at full strength with its reference colour.
- `identity/approved_poses.png`: the owner-approved drawings at one scale (7 frames). Match these.
- `spec_sheet.png`: the pose-target sheet (foot targets on the ground line over a faint silhouette).
- `spec.json`: the criteria `spec_check.py` measures (`specs/ren_walk_inbetweens.json`).
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
- `travel_px_per_frame`: 41.9
- `max_slide_per_loop_px`: 53.8
- `baseline_tolerance_px`: 3
- `ground_y`: 535
- `planted_target_tolerance_px`: 10.7
- `no_flags`: ["stance_not_moving", "slide_unavoidable", "region_colour_drift", "region_size_drift", "out_of_order"]

Checked by eye (the tool cannot):

- [ ] legs visibly swap between frames 1 and 5 (the tool cannot tell left from right)
- [ ] same costume, proportions and colours as the approved poses (region check helps but does not see shapes)

## After drawing

Run (from the repository root; the result goes to `incoming/`, never `assets/`, and shows on the review page as "new, awaiting owner"):

```
python workbench/intake.py <your_sheet_or_folder> --character ren --action walk_8 --replaces walk_keypose --spec specs/ren_walk_inbetweens.json
```

"Meets" means the measurable criteria hold; it is not a judgement of how it looks. The owner decides.
