# Art request 4: ren / caught_game_over

**What:** Redraw or recolour Ren's drifting reactions so colours and proportions match his idle and walk: caught_game_over first, then happy and hurt_stumble.

**Why it is ranked 4 (what it blocks in the sandbox):** caught_game_over plays on every catch; its sleeves and tunic are recoloured (REPORT.md, Phase 5). happy (bigger, rounder head) and hurt_stumble (recoloured face and sleeves) are not used by the sandbox yet but will be by any story beat.

**Now:** `ren/caught_game_over` is *unreviewed*. Owner: "First-pass rework: surprise to sitting, for being caught. Not individually reviewed." See `current.png`.

## Files

- `identity/reference.png`: the identity reference figure (`ren/idle/01.png`).
- `identity/regions.png`: the identity regions the tool checks (hood, hair, face, tunic, sleeves, satchel, trousers, boots), each at full strength with its reference colour.
- `identity/approved_poses.png`: the owner-approved drawings at one scale (7 frames). Match these.
- no pose-target sheet: the criteria below are the target.
- `spec.json`: the criteria `spec_check.py` measures (`requests/ren_reactions/spec.json`).
- `prompt.txt`: an image-generation prompt template.
- `current.png`: the drawings this replaces (contact sheet with the tool's flags).

## Checklist

Measured by the intake command below (`spec_check.py`):

- `frame_count_range`: [8, 14]
- `min_distinct`: 8
- `max_near_duplicates`: 2
- `grounded`: false
- `baseline_tolerance_px`: 3
- `no_flags`: ["region_colour_drift", "region_size_drift"]

Checked by eye (the tool cannot):

- [ ] same face, hood shape and proportions as ren/idle (the region check sees colour and size, not shape)
- [ ] pose changes read clearly at game size (about 200 px tall)

## After drawing

Run (from the repository root; the result goes to `incoming/`, never `assets/`, and shows on the review page as "new, awaiting owner"):

```
python workbench/intake.py <your_sheet_or_folder> --character ren --action caught_game_over_v2 --replaces caught_game_over --spec requests/ren_reactions/spec.json
python workbench/intake.py <sheet> --character ren --action happy_v2 --replaces happy --spec requests/ren_reactions/spec.json
python workbench/intake.py <sheet> --character ren --action hurt_stumble_v2 --replaces hurt_stumble --spec requests/ren_reactions/spec.json
```

"Meets" means the measurable criteria hold; it is not a judgement of how it looks. The owner decides.
