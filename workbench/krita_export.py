"""Krita round trip: export an action (and its redraw spec) as PNG sequences Krita's "Import Animation Frames" loads.

    python workbench/krita_export.py ren walk_keypose --spec specs/ren_walk_inbetweens.json
    python workbench/krita_export.py guard walk --spec specs/guard_walk.json
    python workbench/krita_export.py ren climb_up

Writes out/krita/<character>_<action>/ (see KRITA_STEPS.md written there):
  frames/NN.png   the drawings to keep (keys, shifted by the spec's non-destructive offsets) and BLANK cells to draw
  targets/NN.png  foot/hand targets for each frame + ground line (from the spec, or the action's annotated contacts)
  onion/NN.png    the previous drawing (blue) and next drawing (orange), faint
  ghost/NN.png    a faint current drawing for scale/costume when the spec names one
  ground.png      ground line and cell border, one image
Every image is exactly the action's cell size, so frames come back aligned; bring them back with
  python workbench/intake.py <rendered folder> --character C --action A --replaces X --spec S --as-is
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze as A  # noqa: E402
from diagnostics import font  # noqa: E402

BLUE, RED, GROUND_C = (42, 120, 214, 255), (200, 30, 40, 255), (40, 40, 40, 255)


def tint(frame, rgb, alpha):
    out = np.zeros_like(frame)
    m = frame[..., 3] > A.ALPHA_T
    out[m, :3] = rgb; out[m, 3] = int(alpha * 255)
    return out


def shift_x(frame, dx):
    dx = int(round(dx))
    out = np.zeros_like(frame)
    if dx >= 0: out[:, dx:] = frame[:, :frame.shape[1] - dx]
    else: out[:, :dx] = frame[:, -dx:]
    return out


def targets_image(cell, ground, contacts, label):
    im = Image.new("RGBA", tuple(cell), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.line([(0, ground), (cell[0], ground)], fill=GROUND_C, width=2)
    for name, c in contacts.items():
        x, y = float(c["x"]), float(c["y"]); col = BLUE if name.endswith("_l") else RED
        if c.get("state") == "planted":
            d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=col, outline=(0, 0, 0, 255))
        else:
            d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=col, width=3)
        d.text((x - 20, y + 9), name, fill=col, font=font(12))
    d.text((8, 8), label, fill=(0, 0, 0, 255), font=font(14))
    return im


def pack(character, action, spec_path=None, out_root=None):
    act = A.load_action(character, action)
    cell = [act.frames[0].shape[1], act.frames[0].shape[0]]
    ground = act.ground_y
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8")) if spec_path else None
    out = Path(out_root or (A.OUT / "krita" / f"{character}_{action}"))
    if out.exists():
        shutil.rmtree(out)
    for sub in ("frames", "targets", "onion", "ghost"):
        (out / sub).mkdir(parents=True)
    plan = []
    if spec:
        ground = float(spec.get("ground_y", ground))
        offs = spec.get("key_offsets_x")
        for k, fs in enumerate(spec["frames"]):
            m = re.match(r"key (\d+)", fs["pose"])
            if m and offs is not None:          # an existing key, shifted by the spec's offset
                i = int(m.group(1)) - 1
                plan.append({"frame": k + 1, "kind": "keep", "drawing": act.files[i].name, "offset_x": offs[i],
                             "image": shift_x(act.frames[i], offs[i]), "contacts": fs["contacts"], "pose": fs["pose"]})
            else:
                g = re.search(r"current frame (\d+)", fs.get("source", ""))
                plan.append({"frame": k + 1, "kind": "draw", "image": None, "contacts": fs["contacts"], "pose": fs["pose"],
                             "ghost": act.frames[int(g.group(1)) - 1] if g else None})
    else:
        for k, f in enumerate(act.frames):
            plan.append({"frame": k + 1, "kind": "keep", "drawing": act.files[k].name, "image": f,
                         "contacts": (act.contacts[k] if act.contacts else {}), "pose": f"drawing {act.files[k].name}"})
    blank = np.zeros((cell[1], cell[0], 4), np.uint8)
    n = len(plan)
    for k, p in enumerate(plan):
        name = f"{k + 1:02d}.png"
        Image.fromarray(p["image"] if p["image"] is not None else blank, "RGBA").save(out / "frames" / name)
        targets_image(cell, ground, p["contacts"], f"{k + 1}: {p['pose']}" + ("  (DRAW THIS)" if p["kind"] == "draw" else "")).save(out / "targets" / name)
        on = np.zeros_like(blank)
        for j, rgb in ((k - 1, (42, 120, 214)), (k + 1, (235, 104, 52))):
            q = plan[j % n]
            if q["image"] is not None:
                t = tint(q["image"], rgb, 0.35); m = t[..., 3] > 0; on[m] = t[m]
        Image.fromarray(on, "RGBA").save(out / "onion" / name)
        gh = p.get("ghost")
        Image.fromarray(tint(gh, (120, 120, 120), 0.18) if gh is not None else blank, "RGBA").save(out / "ghost" / name)
    g = Image.new("RGBA", tuple(cell), (0, 0, 0, 0)); d = ImageDraw.Draw(g)
    d.rectangle([0, 0, cell[0] - 1, cell[1] - 1], outline=(160, 160, 160, 255)); d.line([(0, ground), (cell[0], ground)], fill=GROUND_C, width=2)
    g.save(out / "ground.png")
    meta = {"format": "workbench-krita-pack/1", "character": character, "action": action, "spec": spec_path, "cell_size": cell,
            "ground_y": ground, "frames": [{k: v for k, v in p.items() if k not in ("image", "ghost")} for p in plan],
            "bring_back": f"python workbench/intake.py <rendered folder> --character {character} --action <new name> --replaces {action}"
                          + (f" --spec {spec_path}" if spec_path else "") + " --as-is"}
    (out / "pack.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    to_draw = [p["frame"] for p in plan if p["kind"] == "draw"]
    (out / "KRITA_STEPS.md").write_text(STEPS.format(c=character, a=action, w=cell[0], h=cell[1], n=n, draw=", ".join(map(str, to_draw)) or "none",
                                                      back=meta["bring_back"], ground=int(ground)), encoding="utf-8")
    return out, meta


STEPS = """# Drawing {c}/{a} in Krita

Frames to draw: **{draw}** (of {n}). Everything here is {w} x {h} px, the game cell; keep that canvas size.

1. **New document**: File > New, {w} x {h} px, transparent background, 300 ppi is irrelevant (pixels matter).
2. **Load the frames as an animated layer**: File > Import Animation Frames..., *Add images*, select all of
   `frames/01.png ... frames/{n:02d}.png` in order, start 0, step 1. Krita creates one layer with a frame per image
   (blank cells are the ones to draw). Rename it "drawing".
3. **Load the guides** the same way, each into its own layer, and lower their opacity / lock them:
   `targets/*.png` (where planted feet/hands must touch; rings are lifted limbs; the line is the ground at y={ground}),
   `onion/*.png` (previous drawing blue, next drawing orange) and, if present, `ghost/*.png` (current drawing, for scale).
   For a single fixed ground line you can instead use Layer > Import/Export > Import Layer... `ground.png`.
   Krita's own onion skin (Animation > Onion Skins docker) also works on the "drawing" layer.
4. **Draw** the blank frames on the "drawing" layer (or a new layer above it, one keyframe per frame). Keep the feet on the
   targets: filled dots are planted contacts, so the foot must touch the ground exactly there. Don't move or rescale
   the kept drawings.
5. **Hide every guide layer**, then File > Render Animation... > Image Sequence, PNG, "Render as" the full range,
   base name `frame_` into a new empty folder. (Only the drawing layer must be visible.)
6. **Bring it back** through the intake (never into assets/):

       {back}

   `--as-is` keeps your placement because the canvas is the cell; drop it to let the intake re-fit scale and alignment.
   Then open the review page: the new set appears as "new, awaiting owner" next to {c}/{a}, with its report and spec result.
"""


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("character"); p.add_argument("action"); p.add_argument("--spec"); p.add_argument("--out")
    a = p.parse_args(argv)
    out, meta = pack(a.character, a.action, a.spec, a.out)
    print(f"{len(meta['frames'])} frames -> {A.rel(out)} (draw: {[f['frame'] for f in meta['frames'] if f['kind'] == 'draw']}); see KRITA_STEPS.md")


if __name__ == "__main__":
    main()
