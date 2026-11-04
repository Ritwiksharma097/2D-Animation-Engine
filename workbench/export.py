"""Export actions for a game: a packed sprite sheet + JSON per action (edits applied, assets untouched).

    python workbench/export.py ren walk_keypose climb_up jump     # -> out/export/ren/<action>.png/.json
    python workbench/export.py --demo                              # the actions play.html needs

JSON (format workbench-export/1), all in cell px of that action unless named *_game:
  frames[]: rect [x, y, w, h] in the sheet, offset [x, y] = where the rect sits in the cell,
            duration_ms, travel_px (advance when leaving this frame, along facing), contacts (after edits)
  anchor: the cell point that sits on the character's game position (feet on the ground)
  scale: game px per cell px; loop_mode; facing; travel_mode
  path / props: for scene actions, per-frame anchor displacement from the start and the props,
                both relative to the start anchor (so the game can place the ledge)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze as A  # noqa: E402
import props as P  # noqa: E402
import settings as S  # noqa: E402

EXPORT = A.OUT / "export"
PAD = 2


def crop(frame):
    m = frame[..., 3] > 0
    ys, xs = np.nonzero(m)
    if not len(xs):
        return frame[:1, :1], (0, 0)
    x0, y0 = max(0, xs.min() - PAD), max(0, ys.min() - PAD)
    x1, y1 = min(frame.shape[1], xs.max() + 1 + PAD), min(frame.shape[0], ys.max() + 1 + PAD)
    return frame[y0:y1, x0:x1], (int(x0), int(y0))


def pack(images, max_w=2048):
    """Shelf packing, tallest first. Returns sheet image and rects in input order."""
    order = sorted(range(len(images)), key=lambda i: -images[i].shape[0])
    rects, x, y, shelf = [None] * len(images), 0, 0, 0
    for i in order:
        h, w = images[i].shape[:2]
        if x + w > max_w:
            x, y, shelf = 0, y + shelf, 0
        rects[i] = [x, y, w, h]
        x += w; shelf = max(shelf, h)
    W = max(r[0] + r[2] for r in rects); H = max(r[1] + r[3] for r in rects)
    sheet = np.zeros((H, W, 4), np.uint8)
    for img, (x, y, w, h) in zip(images, rects):
        sheet[y:y + h, x:x + w] = img
    return Image.fromarray(sheet, "RGBA"), rects


def export(character, action, out_dir=EXPORT, travel_override=None, scale_override=None):
    act = A.load_action(character, action)
    if travel_override is not None:
        act.travel, act.travel_mode, act.travel_source = float(travel_override), "constant", "export override"
    rep = A.analyze(act)
    info = A.load_manifest()["characters"][character]["actions"][action]
    cell = list(act.frames[0].shape[1::-1])
    crops = [crop(f) for f in act.frames]
    sheet, rects = pack([c for c, _ in crops])
    n = len(act.frames)
    walk = rep["metrics"]["walk"]
    if walk:
        per = walk["travel_used_per_step_px"] or [walk["travel_used_px"]] * len(walk["steps"])
        travel = {i: per[k] for k, (i, j) in enumerate(walk["steps"])}
        travel_mode = act.travel_mode or "recommended constant"
    else:
        travel, travel_mode = {}, "none"
    doc = act.annotations or {}
    scene = doc.get("scene")
    anchor = scene["anchor"] if scene else [cell[0] / 2, act.ground_y]
    frames = []
    for k, ((img, off), rect) in enumerate(zip(crops, rects)):
        frames.append({"rect": rect, "offset": list(off), "duration_ms": round(act.durations_ms[k], 1),
                       "travel_px": round(float(travel.get(k, 0.0)), 2),
                       "contacts": (act.contacts[k] if act.contacts else {}),
                       "source": act.files[k].name, "entry": act.entries[k] if act.entries else k})
    out = {"format": "workbench-export/1", "character": character, "action": action, "image": f"{action}.png",
           "cell_size": cell, "anchor": anchor,
           "scale": scale_override or S.game_scale(character)[0],
           "scale_confirmed": S.game_scale(character)[1], "scale_source": S.game_scale(character)[2],
           "loop_mode": act.loop_mode, "facing": act.facing, "travel_mode": travel_mode, "frames": frames,
           "status_in_manifest": info.get("status"), "suspect_flags": sorted({f["code"] for f in rep["flags"]})}
    if doc.get("events"):
        # named events: 1-based drawing frame in the document -> 0-based played frame index in the export
        entries = act.entries or list(range(n))
        ev = {}
        for name, e in doc["events"].items():
            want = int(e["frame"]) - 1
            k = entries.index(want) if want in entries else min(range(n), key=lambda i: abs(entries[i] - want))
            ev[name] = {**e, "frame": k}
        out["events"] = ev
    if doc.get("jump_timing"):
        out["jump"] = doc["jump_timing"]
    if scene:
        offs = P.path_offsets(scene, n, act.contacts, act.frames)
        ax, ay = anchor
        start = (offs[0][0] + ax, offs[0][1] + ay)
        out["path"] = [[round(o[0] + ax - start[0], 2), round(o[1] + ay - start[1], 2)] for o in offs]
        rel = []
        for p in scene.get("props", []):
            q = dict(p)
            for key in ("front_x", "back_x", "x_left", "x_right"):
                if key in q:
                    q[key] = round(q[key] - start[0], 2)
            for key in ("top_y", "bottom_y", "first_rung_y"):
                if key in q:
                    q[key] = round(q[key] - start[1], 2)
            rel.append(q)
        out["props"] = rel
        out["floor_y"] = round(scene["floor_y"] - start[1], 2)
        out["path_source"] = scene["path"]["type"] + (": " + scene.get("source", "") if scene.get("source") else "")
        if any(q["type"] == "ledge" for q in scene.get("props", [])):
            import ledge_sweep as LS
            _, summ, res = LS.run(character, action, list(range(60, 141)))
            led0 = next(q for q in scene["props"] if q["type"] == "ledge")
            by = {}
            for row in summ["rows"]:
                offs_h = [f["offset"] for f in res[row["pct"]]["frames"]]
                st = (offs_h[0][0] + ax, offs_h[0][1] + ay)
                by[str(int(row["pct"]))] = {"height": row["height_px"], "supported": row["supported"], "supported_2x": row["supported_2x"],
                                            "front_x": round(led0["front_x"] - st[0], 2),
                                            "path": [[round(o[0] + ax - st[0], 2), round(o[1] + ay - st[1], 2)] for o in offs_h]}
            out["paths_by_height"] = by
            out["height_rule"] = {"strict": summ["rule"], "strict_range_pct": summ["supported_pct"],
                                  "loose": summ["rule_2x"], "loose_range_pct": summ["supported_pct_2x"], "note": summ["note"]}
    d = out_dir / character
    d.mkdir(parents=True, exist_ok=True)
    sheet.save(d / f"{action}.png", optimize=True)
    (d / f"{action}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


DEMO = [("ren", "walk_keypose"), ("ren", "climb_up"), ("ren", "climb_down"), ("ren", "jump"), ("ren", "idle")]



def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("character", nargs="?"); p.add_argument("actions", nargs="*")
    p.add_argument("--demo", action="store_true", help="export what out/export/play.html uses")
    a = p.parse_args(argv)
    todo = DEMO if a.demo else [(a.character, x) for x in a.actions]
    if not todo:
        p.error("give CHARACTER ACTION... or --demo")
    if a.demo:   # the guard patrols in the playtest at Ren's scale; his walk speed = stride-based estimate (his contacts walk in place)
        g = A.analyze(A.load_action("guard", "walk"))["metrics"]["walk"]
        export("guard", "idle")       # scale from annotations/_settings.json (guard's is unconfirmed)
        export("guard", "eating")
        o = export("guard", "walk", travel_override=round(g["stride_based_travel_px"], 2))
        print(f"guard/walk: travel {o['frames'][0]['travel_px']} px/frame (stride-based; the drawings themselves walk in place, so it slides)")
    for c, ac in todo:
        o = export(c, ac)
        tr = [f["travel_px"] for f in o["frames"]]
        print(f"{c}/{ac}: {len(o['frames'])} frames, travel {tr} ({o['travel_mode']}) -> {(EXPORT / c / (ac + '.json')).relative_to(A.ROOT)}")


if __name__ == "__main__":
    main()
