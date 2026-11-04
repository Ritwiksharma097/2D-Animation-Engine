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

## Edits (non-destructive)

Fixes live in the same action document and are applied by `workbench/edits.py` (analysis, export)
and by the browser workbench (preview). `assets/` is never changed.

| Field | Level | Meaning |
| --- | --- | --- |
| `frames` order | action | Playback order. An entry may name the same file as another entry. |
| `frames[].hold` | frame | Integer >= 1. The drawing stays on screen for `hold` x `duration_ms`. |
| `frames[].drop` | frame | `true` = kept in the document (so the change is visible) but not played or analysed. |
| `frames[].offset` | frame | `[dx, dy]` in cell px, applied after mirroring. |
| `snap_to_ground` | action, or frame override | Adds a vertical shift so the lowest planted ground foot/heel/toe contact, or, without contacts, the lowest opaque pixel, sits on `ground_anchor.y`. Added to `offset[1]`. |
| `mirror` | action | Flip each frame horizontally about the cell (x' = width - 1 - x). Facing flips, so travel runs the other way. |
| `edits_note` | action | Free text: why the edits were made (auto-suggest writes one). |

Order of operations per frame: mirror, then `offset`, then snap. **Contacts are stored in source
(unedited) coordinates** and transformed with the frame, so changing an offset never invalidates
annotations. Reports list `entries` (document index of each analysed frame) because frame numbers
in a report count played frames only.

Auto-suggest for idles (`python workbench/edits.py suggest-idle <character> <action> --write`):
consecutive frames whose silhouette is within the near-duplicate threshold (3%) of the run's first
drawing become one entry with `hold` = run length; the absorbed frames are marked `drop`. Each held
pose lasts run length x base duration x 2, clamped to 250-1500 ms. It refuses to overwrite a
document that already has contacts or holds.

## Scenes (props and paths)

`scene` in an action document places the action in a world with props. Units are the action's own
cell px (Ren's climbs: game px / 0.4777). Checked by `workbench/props.py` and drawn by the page's
"scene" preview.

```json
"scene": {
  "floor_y": 1243.5,
  "anchor": [256, 439.6],
  "props": [
    {"type": "ledge", "id": "ledge", "front_x": 967.1, "back_x": 1394.2, "top_y": 1046.7,
     "cap": {"overhang": 16.7, "thickness": 16.7}},
    {"type": "ladder", "id": "ladder", "x_left": 920, "x_right": 1080, "bottom_y": 1000,
     "top_y": 466, "first_rung_y": 1000, "rung_spacing": 89}
  ],
  "path": {"type": "line", "from": [889.7, 1243.5], "to": [1063.4, 1046.7]}
}
```

- The frame's cell is placed so its `anchor` point sits on the path. `line`: played frame k at
  t = k/(n-1) (optional `t` list). `points`: one position per frame. `vertical_loop`: `from`, rising
  `rise_per_frame`, for `cycles` loops (ladders). `from_contacts`: `base` is another path; y is
  replaced per frame so planted contacts with a horizontal `surface` (`ground`, `ledge_top`) sit
  on it, x holds shared planted contacts fixed between frames and is shifted just enough to put a
  `ledge_top` contact over the ledge.
- Surfaces a contact can name: `ground`, `ledge_top`, `ledge_face` (cap front/underside and body
  face), `ladder_rung`, `ladder_rail`, or a surface id (`ledge.top`). Solids: floor, ledge cap and
  body. Ladders are behind the character, so overlapping them is not clipping.
- Flags: `body_clips_prop` (pixels > 4 px inside a solid), `unsupported_body` (no pixel within
  6 px of any surface), `contact_off_surface` (planted contact > 6 px from its surface: "reaching
  into air" for hands, "pushing off nothing" for feet), `contact_in_prop`, and
  `planted_contact_slides` (a planted contact moves > 6 px along its surface between frames).

## Identity regions (`annotations/<character>/_identity.json`)

```json
{"format": "workbench-identity/1", "character": "ren", "reference": "ren/idle/01.png",
 "regions": {"hood": {"seed": [319, 142]}, "hair": {"seed": [392, 142]}}}
```

Seeds are pixels of the identity reference. `workbench/regions.py` learns each region's colour (Lab
mean of a 7x7 patch at the seed) and vertical band (the extent of the seed's connected same-colour
patch in the reference, as a fraction of figure height, +-0.06). In any frame the region is every
opaque pixel within 14 Lab units of that colour inside the band. Per region and action: share of the
figure relative to the reference's share (flag outside 0.6-1.6) and mean colour distance (flag
> 6 Lab). These replace the whole-figure palette flags in reports.

## Export (`out/export/<character>/<action>.json` + `.png`)

Written by `workbench/export.py` after edits are applied. `format: workbench-export/1`;
`image` (packed sheet), `cell_size`, `anchor` (cell point on the game position), `scale` (game px
per cell px), `loop_mode`, `facing`, `travel_mode`, `frames[]` with `rect` [x, y, w, h] in the
sheet, `offset` (rect's position in the cell), `duration_ms` (hold applied), `travel_px` (advance
when leaving the frame), `contacts`, `source`, `entry`. Scene actions add `path` (per-frame anchor
displacement from the start), `props` and `floor_y` relative to the start anchor, and
`path_source`. `suspect_flags` lists the analysis flag codes so a game import can warn.

## Owner reviews (`annotations/_reviews.json`)

```json
{"format": "workbench-reviews/1",
 "reviews": {"guard/idle": {"verdict": "needs work", "comment": "...", "updated": "2026-11-04T11:11:19"}}}
```

`verdict` is one of `approved`, `needs work`, `rejected`, `unsure` or empty. Written only by the
review page through `serve.py` (`POST /api/review`, merged per action). The manifest's `status` is
never changed by it.

## Settings (`annotations/_settings.json`)

Values the owner decides, in one place. `characters.<name>.game_scale` (game px per cell px),
`confirmed` (has the owner set it?) and `source`. `export.py` uses it for every export, and the
review page shows and edits it. `open_decisions` records where each open decision lives
(guard ledge reading, Ren's climb step-in, walk timing, new frames), so each stays changeable in
one place.

## Intake registry (`incoming/<character>/<action>/intake.json`)

`format: workbench-intake/1`; `status` ("new, awaiting owner"); `source` (sheet or folder);
`method` (grid CxR, connected components, folder); `replaces`; `spec`; `fitted_to` (target height,
cell, ground y, head x and where they came from); `scale` (uniform); `frames[]` with `file`,
`offset` (where the trimmed figure was placed in the cell), `size`, `clipped_by_cell`; `alignment`.
Reviews of intakes use the key `<character>/incoming__<action>`.

## Events (annotation `events` -> export `events`)

`"events": {"pickup": {"frame": 4, "point": [400.9, 519.0], "note": "..."}}` in an action document;
`frame` is the 1-based drawing number. The export converts it to the 0-based played-frame index.
`point` (optional, cell px of that drawing, before edits) is passed to the runtime as a world point.

## Levels (`levels/<name>.json`, format `workbench-level/1`)

Game px, y grows downward. Read by `runtime/level.js`, edited by `workbench/level_editor.html`,
saved through `serve.py` (`POST /api/level?name=`).

```json
{"format": "workbench-level/1", "name": "demo", "size": [2600, 520],
 "floors":    [{"id": "A", "x0": 0, "x1": 1300, "y": 470}, {"id": "B", "x0": 1400, "x1": 2600, "y": 470}],
 "ledges":    [{"id": "L1", "x0": 500, "x1": 700, "top": 376, "on": "A"}],
 "platforms": [{"id": "P", "x0": 1900, "x1": 2200, "top": 300}],
 "ladders":   [{"id": "LD", "x": 1860, "from": "B", "to": "P", "rung_spacing": 32}],
 "hotspots":  [{"id": "item", "x": 2100, "on": "P", "kind": "item", "item": "key", "use": "interact"}],
 "rules":     {"jump_max_gap": 140, "jump_max_rise": 12}}
```

- **floors:** walkable segments. A gap is simply where no floor exists.
- **ledges:** solid blocks standing on a floor (`on`). The front face is `x0`, the back face `x1`;
  both can be climbed (the back is the climb mirrored).
- **platforms:** floating surfaces, reached by jumping or by ladder.
- **ladders:** `from` a floor (or surface) id `to` a surface id, at `x`.
- **hotspots:** items or use points on a surface (`on`).
- **rules:** jump limits and transition costs; they override `runtime/level.js` `DEF_RULES`.

### Scene keys (optional; read by `runtime/scene.js`, step 30)

```json
"layers":    [{"id": "far_hills", "parallax": 0.2, "depth": -200, "alpha": 1, "rects": [{"x": 0, "y": 300, "w": 420, "h": 170, "color": "#d9e2e6"}]}],
"occluders": [{"id": "pillar", "x0": 560, "x1": 610, "y0": 120, "y1": 470, "color": "#8c8c8c", "alpha": 0.95, "blocks_sight": false}],
"hiding_spots": [{"id": "crate", "on": "A", "x0": 980, "x1": 1070, "height": 110, "kind": "behind", "reveal_radius": 45}],
"doors":     [{"id": "D1", "on": "A", "x": 1730, "to": {"level": "scene_b", "door": "D0"}}, {"id": "out", "on": "B", "x": 1140, "kind": "exit"}]
```

- **layers:** flat-colour rectangles in screen space shifted by `camera x * parallax` (0 = fixed sky,
  1 = moves with the world, > 1 = foreground). `depth` < 0 draws behind the world, > 0 in front.
- **occluders:** world-space shapes drawn in front of characters (depth 50); `blocks_sight` adds them
  to the guard's line-of-sight solids.
- **hiding_spots:** a character holding a pose tagged `hide` inside `x0..x1` on `on` is hidden: silent,
  passable, and seen only within `reveal_radius` game px. `kind: "behind"` draws the spot in front of
  him (depth 5), `"in"` behind (depth -5).
- **doors:** `to: {level, door}` moves to that door of another level file (with a fade); `kind: "exit"`
  ends the run. `width` (60) and `height` (150) are for clicking and drawing.
- Depth sorting: drawables sort by `depth`, then feet `y`, then insertion order (`depthSort`).

`compileLevel` turns floors into **walk regions** split by the ledges standing on them, e.g.
`A#0` is left of L1 and `A#1` right of it. A region's sides are `face` (stop before the ledge,
allowing the 40 cell px front band) or `edge` (stop 10 px from a drop). `navGraph` lists the
transitions (climb up / down per face, jump, ladder), judging each against the character's drawings.

## Sequences (level key `sequences`, `runtime/sequence.js`)

```json
"sequences": [{"id": "read_sign", "trigger": {"on": "hotspot", "id": "sign"}, "once": false, "skippable": true,
               "requires": {"has_key": true},
               "steps": [{"do": "face", "who": "ren", "toward": 330}, {"do": "emote", "who": "ren", "kind": "?", "ms": 700, "wait": true},
                         {"do": "walk", "who": "ren", "x": 260}, {"do": "play", "who": "guard", "role": "angry"}, {"do": "wait", "ms": 500},
                         {"do": "camera", "x": 1000, "ms": 900}, {"do": "camera", "who": "ren", "ms": 700},
                         {"do": "fade", "to": 1, "ms": 300}, {"do": "fade", "to": 0, "ms": 300},
                         {"do": "flag", "name": "read_sign"}, {"do": "sound", "id": "chime"}]}]
```

- **trigger:** `{"on": "level_start"}`, `{"on": "hotspot", "id": ...}`, or `{"on": "event", "name": ...}` (the
  page fires events it cares about). `once` defaults to true; `requires` lists flags that must match.
- **steps** run in order; each waits until done (`walk` / `play` / `face`: the actor is idle; `wait`,
  `camera`, `fade`: `ms`; `emote`: only with `"wait": true`). `camera` centres `x` or an actor with an
  ease; while a sequence runs it owns the camera and player input is ignored.
- **skip** (default allowed) applies every remaining end state at once: walks teleport to `x`, plays
  stop, faces turn, fades jump to `to`, flags are set, emotes clear.
- **emote kinds:** `!`, `?`, `heart`, `...`, `zZz` (drawn by `runtime/emote.js`).

## Sounds (`runtime/sound.js`)

`{"defs": {"step": {"freq": 180, "ms": 40, "type": "triangle", "gain": 0.04, "slide": 0}}, "ren": {"frame:ren/walk_keypose:0": "step",
"bump": "bump", "state:jump": "jump"}}`. Keys per actor: a clip or runtime event name, `state:<to>`, or
`frame:<clip key>:<0-based frame>`. Each id is a placeholder WebAudio beep from `defs` until real
sounds exist; the AudioContext starts on the first click; mute is stored in `localStorage`.
