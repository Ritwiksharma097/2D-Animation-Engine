# Workbench data formats

All coordinates are **cell pixels** of the source frame (origin top-left, x right, y down).
The manifest's `cell_size` is `[640, 576]` and `ground_y` is `535`. Game-space values are cell
values multiplied by the character's `game_scale` (Ren used `0.4777` in the old demos).

Files described here live in `annotations/<character>/<action>.json`, never in `assets/`.
One file holds both the action settings and the per-frame annotations so the browser workbench
can save and download a single document. Every field except `format`, `character`, `action`
and `frames[].file` is optional; tools fill defaults from `assets/manifest.json`.

## Action document

```json
{
  "format": "workbench-action/1",
  "character": "ren",
  "action": "walk_keypose",
  "source_dir": "ren/walk_keypose",
  "cell_size": [640, 576],
  "loop_mode": "loop",
  "default_duration_ms": 120,
  "ground_anchor": { "y": 535 },
  "facing": "right",
  "travel": { "mode": "constant", "px_per_frame": 41.9 },
  "frames": [
    {
      "file": "01.png",
      "duration_ms": 120,
      "contacts": {
        "foot_l": { "x": 212.0, "y": 533.0, "state": "planted", "surface": "ground" },
        "foot_r": { "x": 318.0, "y": 528.0, "state": "free" }
      },
      "note": "contact pose, left foot forward"
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `format` | Always `workbench-action/1`. Bump the number for incompatible changes. |
| `source_dir` | Folder under `assets/` holding `NN.png` frames. |
| `loop_mode` | `loop` (last → first), `pingpong` (1..N..2), or `once`. |
| `default_duration_ms` | Used for frames without `duration_ms`. |
| `ground_anchor.y` | Ground line in cell px. Planted ground contacts should sit on it. |
| `facing` | `right` or `left`; travel is positive in the facing direction. |
| `travel.mode` | `none` (in place), `constant` (`px_per_frame` cell px every frame), `per_frame` (`px_per_frame` is a list, one value per frame: the advance applied when *leaving* that frame), or `from_contacts` (derived from planted contacts, see below). |
| `frames[].file` | File name inside `source_dir`. Order in the list is playback order, so frames can be reordered or repeated without touching assets. |
| `frames[].duration_ms` | Hold time for this frame. |
| `frames[].contacts` | Named contact points (see below). Missing names are "not annotated", not "free". |
| `frames[].note` | Free text. |

## Contact points

Keys are names; conventional names are `foot_l`, `foot_r`, `hand_l`, `hand_r`, `toe_l`,
`heel_l` (etc.). `_l`/`_r` are the character's own left/right, not screen side.
Tools treat any name starting with `foot_`, `toe_` or `heel_` as a foot.

| Field | Meaning |
| --- | --- |
| `x`, `y` | Point in cell px. For a foot, the point that touches the surface (ball/heel). |
| `state` | `planted` (touching and should not move in world space), `free` (in the air or sliding on purpose), or `unknown`. |
| `surface` | What it touches when planted. `ground` now. Reserved for later: `ladder_rung`, `ledge_top`, `ledge_face`, `prop:<id>`. |
| `prop` | Reserved: id of a scene prop (ladder, ledge) whose geometry will be defined in a future `scenes/` format. Tools must ignore unknown fields. |

### Travel derived from contacts (`travel.mode = "from_contacts"`)

For the step from frame *i* to frame *i+1*: if a contact with the same name is `planted` in both
frames on the same surface, the character must advance by `x_i - x_{i+1}` (times `+1` facing
right, `-1` facing left) for that point to stay fixed in world space. With more than one shared
planted contact the mean is used, and the reported slide is the worst of them (all should stay put).
A foot that rolls heel-to-toe is best annotated as `heel_x` and `toe_x` points: the heel is shared
from heel-strike to flat, the toe from flat to push-off. Steps with no shared planted
contact fall back to the mean of the derived steps (and are flagged).

## Report (`out/<character>/<action>/report.json`)

Written by `workbench/analyze.py`. Top level: `character`, `action`, `source`, `frame_count`,
`settings` (travel, thresholds), `metrics` (per-frame arrays), `flags` (list of
`{"level": "suspect", "code": ..., "frames": [...], "message": ...}`), `limits` (one sentence
per heuristic saying what it cannot tell), and `summary` (plain English). Flags are only ever
`suspect`; absence of a flag is not a pass.
