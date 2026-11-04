# Art request 2: guard / idle

**What:** A calm, grumpy breathing idle in 6 drawings (the timing comes from the edit layer, so no repeated drawings are needed).

**Why it is ranked 2 (what it blocks in the sandbox):** Plays at both ends of every patrol (1.5 s each) and while he is suspicious. Rejected: much too fast, about 4-5 distinct drawings repeated.

**Now:** `guard/idle` is *rejected*. Owner: "Much too fast. Analysis suggests only ~3-4 distinct drawings." See `current.png`.

## Files

- `identity/reference.png`: the identity reference figure (`guard/concept.png`).
- `identity/regions.png`: the identity regions the tool checks (helmet, armour, tabard, face, moustache, gloves), each at full strength with its reference colour.
- `identity/approved_poses.png`: the owner-approved drawings at one scale (6 frames). Match these.
- no pose-target sheet: the criteria below are the target.
- `spec.json`: the criteria `spec_check.py` measures (`requests/guard_idle/spec.json`).
- `prompt.txt`: an image-generation prompt template.
- `current.png`: the drawings this replaces (contact sheet with the tool's flags).

## Checklist

Measured by the intake command below (`spec_check.py`):

- `frame_count_range`: [6, 8]
- `min_distinct`: 5
- `max_near_duplicates`: 1
- `grounded`: true
- `baseline_tolerance_px`: 3
- `feet_still_px`: 4
- `breathing_pct`: [0.4, 3.0]
- `no_flags`: ["out_of_order"]

Checked by eye (the tool cannot):

- [ ] he stays grumpy and recognisably the same guard as his approved happy / interact / eating actions
- [ ] the motion reads as breathing, not as a jitter; feet do not move at all

## After drawing

Run (from the repository root; the result goes to `incoming/`, never `assets/`, and shows on the review page as "new, awaiting owner"):

```
python workbench/intake.py <your_sheet_or_folder> --character guard --action idle_v2 --replaces idle --spec requests/guard_idle/spec.json
```

"Meets" means the measurable criteria hold; it is not a judgement of how it looks. The owner decides.
