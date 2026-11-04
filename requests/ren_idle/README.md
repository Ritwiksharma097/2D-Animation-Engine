# Art request 5: ren / idle

**What:** An idle that does something: breathing plus a blink and a small glance or satchel-strap adjust, 8 drawings, feet planted.

**Why it is ranked 5 (what it blocks in the sandbox):** Ren stands still between clicks; the approved idle is one still drawing (it 'does nothing'). Not wrong, just lifeless.

**Now:** `ren/idle` is *approved*. Owner: "Accepted as an identity match for the walk. It is one still drawing (GPT repeated it 14 times), so later the owner noted the idle 'does nothing'." See `current.png`.

## Files

- `identity/reference.png`: the identity reference figure (`ren/idle/01.png`).
- `identity/regions.png`: the identity regions the tool checks (hood, hair, face, tunic, sleeves, satchel, trousers, boots), each at full strength with its reference colour.
- `identity/approved_poses.png`: the owner-approved drawings at one scale (7 frames). Match these.
- no pose-target sheet: the criteria below are the target.
- `spec.json`: the criteria `spec_check.py` measures (`requests/ren_idle/spec.json`).
- `prompt.txt`: an image-generation prompt template.
- `current.png`: the drawings this replaces (contact sheet with the tool's flags).

## Checklist

Measured by the intake command below (`spec_check.py`):

- `frame_count_range`: [6, 10]
- `min_distinct`: 6
- `max_near_duplicates`: 1
- `grounded`: true
- `baseline_tolerance_px`: 3
- `feet_still_px`: 4
- `breathing_pct`: [0.4, 3.0]
- `height_vs_reference`: [0.97, 1.03]
- `no_flags`: ["region_colour_drift", "region_size_drift", "out_of_order"]

Checked by eye (the tool cannot):

- [ ] frame 1 is the approved idle drawing (identity reference) or indistinguishable from it
- [ ] the glance can be the 'looks at the player' hint the game wants

## After drawing

Run (from the repository root; the result goes to `incoming/`, never `assets/`, and shows on the review page as "new, awaiting owner"):

```
python workbench/intake.py <your_sheet_or_folder> --character ren --action idle_v2 --replaces idle --spec requests/ren_idle/spec.json
```

"Meets" means the measurable criteria hold; it is not a judgement of how it looks. The owner decides.
