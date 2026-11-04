"""Redraw specs: pose-target sheets + JSON specs for drawings that must be redone (not art).

    python workbench/specs.py guard_walk      # -> specs/guard_walk.json + specs/guard_walk.png
    python workbench/specs.py ren_inbetweens  # -> specs/ren_walk_inbetweens.json + .png
    python workbench/specs.py all

Check new frames against a spec with:  python workbench/spec_check.py specs/guard_walk.json <folder of NN.png>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze as A  # noqa: E402
from diagnostics import AQUA, BLUE, INK, MUTED, ORANGE, RED, font, header, stack  # noqa: E402

SPECS = A.ROOT / "specs"
POSES = ["contact", "down", "passing", "up"]


def figure_height(frames):
    return float(np.median([np.ptp(np.nonzero((f[..., 3] > A.ALPHA_T).any(axis=1))[0]) + 1 for f in frames]))


def walk_targets(H, cx, ground, step_frac=0.36, frames=8):
    """Contact/down/passing/up x2. Planted feet move back exactly `travel` per frame, so constant travel can't slide."""
    S = step_frac * H
    v = 2 * S / frames
    bob = {"contact": 0.0, "down": 0.03 * H, "passing": -0.01 * H, "up": -0.02 * H}   # +y = lower
    out = []
    for k in range(frames):
        pose = POSES[k % 4]
        lead, trail = ("l", "r") if k < 4 else ("r", "l")    # legs swap on the second step
        j = k % 4
        stance_x = cx + S / 2 - j * v                       # the leading foot is the stance foot through the step
        c = {}
        if pose == "contact":
            c[f"heel_{lead}"] = {"x": cx + S / 2, "y": ground, "state": "planted"}
            c[f"toe_{trail}"] = {"x": cx - S / 2, "y": ground, "state": "planted"}
        elif pose == "down":
            c[f"foot_{lead}"] = {"x": stance_x, "y": ground, "state": "planted"}
            c[f"toe_{trail}"] = {"x": cx - S / 2 + 0.5 * v, "y": ground - 0.02 * H, "state": "free"}
        elif pose == "passing":
            c[f"foot_{lead}"] = {"x": stance_x, "y": ground, "state": "planted"}
            c[f"foot_{trail}"] = {"x": cx, "y": ground - 0.06 * H, "state": "free"}
        else:
            c[f"toe_{lead}"] = {"x": stance_x, "y": ground, "state": "planted"}
            c[f"heel_{trail}"] = {"x": cx + S / 2 - 0.3 * v, "y": ground - 0.04 * H, "state": "free"}
        out.append({"frame": k + 1, "pose": pose, "leading_leg": lead, "contacts": {n: {**d, "x": round(d["x"], 1), "y": round(d["y"], 1)} for n, d in c.items()},
                    "hip_y": round(ground - 0.5 * H + bob[pose], 1)})
    return out, S, v


def walk_criteria(n, travel, S, ground):
    return {
        "frame_count": n, "distinct_poses": n, "near_duplicates": 0, "steps_per_loop": 2,
        "max_min_stride_ratio": 0.45, "max_pose_change_cv": 0.35,
        "travel_px_per_frame": round(travel, 2), "max_slide_per_loop_px": round(0.1 * travel * n, 1),
        "baseline_tolerance_px": 3, "ground_y": ground,
        "planted_target_tolerance_px": round(0.12 * S, 1),
        "no_flags": ["stance_not_moving", "slide_unavoidable", "region_colour_drift", "region_size_drift", "out_of_order"],
        "manual": ["legs visibly swap between frames 1 and 5 (the tool cannot tell left from right)",
                   "same costume, proportions and colours as the approved poses (region check helps but does not see shapes)"],
    }


def draw_sheet(title, notes, frames_spec, ghosts, ground, cell, path, extra_lines=()):
    W, Hc = cell
    scale = 0.5
    tw, th = int(W * scale), int(Hc * scale)
    sheet = Image.new("RGB", (4 * tw, 2 * (th + 40)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for k, fs in enumerate(frames_spec):
        x0, y0 = (k % 4) * tw, (k // 4) * (th + 40)
        g = ghosts[k]
        if g is not None:
            gi = Image.fromarray(g, "RGBA").resize((tw, th), Image.LANCZOS)
            a = gi.getchannel("A").point(lambda v: int(v * 0.18))
            gi.putalpha(a)
            sheet.paste(gi, (x0, y0 + 40), gi)
        gy = y0 + 40 + ground * scale
        d.line([(x0, gy), (x0 + tw, gy)], fill=INK, width=2)
        d.line([(x0, y0 + 40 + fs["hip_y"] * scale), (x0 + 40, y0 + 40 + fs["hip_y"] * scale)], fill=ORANGE, width=2)
        d.text((x0 + 42, y0 + 40 + fs["hip_y"] * scale - 7), "hip", fill=ORANGE, font=font(10))
        for name, c in fs["contacts"].items():
            px, py = x0 + c["x"] * scale, y0 + 40 + c["y"] * scale
            col = BLUE if name.endswith("_l") else RED
            if c["state"] == "planted":
                d.ellipse([px - 6, py - 6, px + 6, py + 6], fill=col, outline=INK)
            else:
                d.ellipse([px - 6, py - 6, px + 6, py + 6], outline=col, width=2)
            d.text((px - 18, py + 8), name, fill=col, font=font(10))
        d.text((x0 + 4, y0 + 4), f"{fs['frame']}: {fs['pose']}" + (f"  (lead {fs['leading_leg']})" if fs.get("leading_leg") else ""), fill=INK, font=font(14))
        if fs.get("source"):
            d.text((x0 + 4, y0 + 22), fs["source"], fill=MUTED, font=font(10))
        d.rectangle([x0, y0, x0 + tw - 1, y0 + th + 39], outline=(225, 225, 225))
    hd = header(sheet.width, [title] + list(notes) + list(extra_lines), 12)
    stack([hd, sheet]).save(path, optimize=True)


def guard_walk():
    act = A.load_action("guard", "walk")         # edited (snapped to ground)
    H = figure_height(act.frames)
    ground = act.ground_y
    import intake
    cx = round(float(np.median([intake.head_x(f) for f in act.frames])), 1)   # targets centred where intake puts the head
    frames_spec, S, v = walk_targets(H, cx, ground)
    # faint silhouette: the current drawing closest in stride to each target (scale and costume reference only)
    strides = [A.foot_clusters(f)["stride"] for f in act.frames]
    want = {"contact": max(strides), "down": np.percentile(strides, 60), "passing": min(strides), "up": np.percentile(strides, 40)}
    ghosts = []
    for fs in frames_spec:
        k = int(np.argmin([abs(s - want[fs["pose"]]) for s in strides]))
        ghosts.append(act.frames[k]); fs["source"] = f"faint: current frame {k + 1} (scale/costume only)"
    spec = {"format": "workbench-spec/1", "character": "guard", "action": "walk", "replaces": "guard/walk (rejected)",
            "cell_size": [640, 576], "ground_y": ground, "head_x": cx, "figure_height_px": round(H, 1), "step_length_px": round(S, 1),
            "travel_px_per_frame": round(v, 2), "frames": frames_spec,
            "criteria": {**walk_criteria(8, v, S, ground), "no_flags": ["stance_not_moving", "slide_unavoidable", "out_of_order"],
                         "identity_note": "Region colour/size checks are left out for the guard: his only reference is concept art whose tabard differs from every sprite; compare with his approved actions by eye."},
            "how": "Draw 8 frames on 640x576 transparent cells, feet on y=%d, facing right. Planted feet (filled dots) must touch the "
                   "ground at the marked x; free feet (rings) are lifted about that much. The leading leg swaps at frame 5. "
                   "Step length = 0.36 x figure height, travel %.1f px per frame, bob: down lowest, up highest." % (ground, v)}
    SPECS.mkdir(exist_ok=True)
    (SPECS / "guard_walk.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
    draw_sheet("Guard walk redraw spec: 8 frames, contact / down / passing / up, legs swap at frame 5",
               [f"Figure height {H:.0f}px, step {S:.0f}px (0.36 H), travel {v:.1f} px/frame: planted feet move back exactly {v:.1f}px per frame, so this speed can't slide.",
                "Filled dot = planted foot target on the ground line; ring = lifted foot (approximate). Blue = leg l, red = leg r. Orange tick = hip height (bob).",
                "Check new frames:  python workbench/spec_check.py specs/guard_walk.json <folder>"],
               frames_spec, ghosts, ground, (640, 576), SPECS / "guard_walk.png")
    return spec


def ren_inbetweens(old_travel=41.9):
    act = A.load_action("ren", "walk_keypose")
    keys = act.contacts
    d = [98.0, 70.0, 108.0, 81.0]                                 # contact-derived stance travel between keys (annotated)
    per_cycle = sum(d)
    even = per_cycle / 4
    dx = [0.0]
    for i in range(3):
        dx.append(dx[-1] + d[i] - even)                           # key offsets that make every key interval equal
    frames_spec, ghosts = [], []
    for i in range(4):
        kc = {n: {**c, "x": round(float(c["x"]) + dx[i], 1)} for n, c in keys[i].items()}
        frames_spec.append({"frame": 2 * i + 1, "pose": f"key {i + 1} (existing drawing)", "offset_x": round(dx[i], 2), "contacts": kc,
                            "hip_y": 535 - 0.5 * 420, "source": f"existing walk_keypose {i + 1:02d}.png, shifted {dx[i]:+.1f}px"})
        ghosts.append(np.roll(act.frames[i], int(round(dx[i])), axis=1))
        j = (i + 1) % 4
        nxt = {n: {**c, "x": float(c["x"]) + dx[j]} for n, c in keys[j].items()}
        legs_a = {n[-1] for n, c in kc.items() if c["state"] == "planted"}
        legs_b = {n[-1] for n, c in nxt.items() if c["state"] == "planted"}
        stance = (legs_a & legs_b) or legs_b
        mid = {}
        for n, c in kc.items():          # stance leg: its planted points move back half an interval
            if n[-1] in stance and c["state"] == "planted":
                mid[n] = {"x": round(c["x"] - even / 2, 1), "y": c["y"], "state": "planted"}
        for leg in {"l", "r"} - stance:  # swing leg: half way between its two key positions, lifted
            pa = [c for n, c in kc.items() if n[-1] == leg]; pb = [c for n, c in nxt.items() if n[-1] == leg]
            if pa and pb:
                xa, xb = np.mean([c["x"] for c in pa]), np.mean([c["x"] for c in pb])
                mid[f"foot_{leg}"] = {"x": round(float(xa + xb) / 2, 1), "y": round(float(min(min(c["y"] for c in pa), min(c["y"] for c in pb))) - 25, 1), "state": "free"}
        frames_spec.append({"frame": 2 * i + 2, "pose": f"in-between {i + 1}->{j + 1} (NEW)", "contacts": mid, "hip_y": 535 - 0.5 * 420,
                            "source": "faint: key %d (draw the half-way pose)" % (i + 1)})
        ghosts.append(None)
    residual = (even / 2 - old_travel)
    spec = {"format": "workbench-spec/1", "character": "ren", "action": "walk_keypose_8", "based_on": "ren/walk_keypose (approved; keys unchanged)",
            "cell_size": [640, 576], "ground_y": 535, "key_offsets_x": [round(v, 2) for v in dx],
            "stance_travel_between_keys": d, "travel_px_per_frame_exact": round(even / 2, 2), "old_travel_px_per_frame": old_travel,
            "residual_slide_per_frame_at_old_travel_px": round(residual, 2), "frames": frames_spec,
            "criteria": {**walk_criteria(8, old_travel, even, 535), "max_slide_per_loop_px": round(abs(residual) * 8 + 4 * 8, 1)},
            "truth": (f"The 4 keys move the stance foot {per_cycle:.0f} cell px per cycle; 8 frames at {old_travel} px/frame cover {8 * old_travel:.0f}. "
                      f"No in-betweens make that exactly slide-free. With the key offsets {['%+.1f' % v for v in dx]} (non-destructive edits) "
                      f"every key interval becomes {even:.1f}px, so the in-betweens put the stance foot half way ({even / 2:.1f}px per frame). At "
                      f"{old_travel} px/frame the residual slide is {residual:.1f} cell px (~{residual * 0.4777:.1f} game px) per frame, under the 4 px "
                      f"slide tolerance; {even / 2:.1f} px/frame (= {even / 2 * 0.4777:.1f} game px) is exactly slide-free.")}
    SPECS.mkdir(exist_ok=True)
    (SPECS / "ren_walk_inbetweens.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
    draw_sheet("Ren 4-pose walk: the 4 in-betweens (even frames are NEW; odd frames are the approved keys, shifted)",
               [spec["truth"], "Filled dot = planted target (stance foot half way between the keys), ring = swing foot (approximate, lifted ~25px).",
                "Check new frames:  python workbench/spec_check.py specs/ren_walk_inbetweens.json <folder with all 8 frames>"],
               frames_spec, ghosts, 535, (640, 576), SPECS / "ren_walk_inbetweens.png")
    return spec


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("which", choices=["guard_walk", "ren_inbetweens", "all"])
    a = p.parse_args(argv)
    if a.which in ("guard_walk", "all"):
        s = guard_walk(); print(f"specs/guard_walk.json: travel {s['travel_px_per_frame']} px/frame, step {s['step_length_px']} px")
    if a.which in ("ren_inbetweens", "all"):
        s = ren_inbetweens(); print("specs/ren_walk_inbetweens.json:", s["truth"])


if __name__ == "__main__":
    main()
