# Art request 6: guard / ladder_up

**What:** An 8-drawing back-view ladder cycle that climbs two rungs: diagonal hand and foot move together, then swap.

**Why it is ranked 6 (what it blocks in the sandbox):** Not used by the sandbox (the guard AI never climbs). Rejected; the current cycle keeps his feet at one height, so it cannot land on rungs.

**Now:** `guard/ladder_up` is *rejected*. Owner: "Bad. Ladder down was this sequence reversed; also bad." See `current.png`.

## Files

- `identity/reference.png`: the identity reference figure (`guard/concept.png`).
- `identity/regions.png`: the identity regions the tool checks (helmet, armour, tabard, face, moustache, gloves), each at full strength with its reference colour.
- `identity/approved_poses.png`: the owner-approved drawings at one scale (6 frames). Match these.
- `spec_sheet.png`: the pose-target sheet (foot targets on the ground line over a faint silhouette).
- `spec.json`: the criteria `spec_check.py` measures (`specs/guard_ladder.json`).
- `prompt.txt`: an image-generation prompt template.
- `current.png`: the drawings this replaces (contact sheet with the tool's flags).

## Checklist

Measured by the intake command below (`spec_check.py`):

- `frame_count`: 8
- `rise_per_cycle_from_contacts`: 134.6
- `rise_tolerance_px`: 10.1
- `foot_height_range_min_px`: 50.5

Checked by eye (the tool cannot):

- [ ] back view: diagonal limbs move together (right hand with left foot, then left hand with right foot)
- [ ] grippers stay on their rung while the body rises; the cycle loops (frame 8 leads into frame 1 one rung higher)

## After drawing

Run (from the repository root; the result goes to `incoming/`, never `assets/`, and shows on the review page as "new, awaiting owner"):

```
python workbench/intake.py <your_sheet_or_folder> --character guard --action ladder_up_v2 --replaces ladder_up --spec specs/guard_ladder.json
```

"Meets" means the measurable criteria hold; it is not a judgement of how it looks. The owner decides.
