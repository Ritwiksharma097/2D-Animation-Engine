"""Ladders end to end: rise from rung contacts, cycle count for a ladder height, rung landing checks, and a redraw spec.

    python workbench/ladder.py check guard ladder_up --rungs 8      # -> out/guard/ladder_up/ladder.{json,png}
    python workbench/ladder.py spec                                  # -> specs/guard_ladder.{json,png}

A looping climb rises a fixed amount per cycle; a ladder of N rungs takes N / rungs_per_cycle cycles. While a hand or
foot grips a rung its cell y must move DOWN by exactly the body's rise (the vertical twin of walk travel), so the
rise per frame can be measured from the planted rung contacts.
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
import props as P  # noqa: E402

SPECS = A.ROOT / "specs"


def contact_rise(act) -> dict:
    """Per step: body rise implied by rung contacts planted in both frames (cell y increase), and their spread."""
    n = len(act.frames)
    rows = []
    for k in range(n):
        a, b = act.contacts[k] or {}, act.contacts[(k + 1) % n] or {}
        d = [float(b[name]["y"]) - float(c["y"]) for name, c in a.items()
             if c.get("state") == "planted" and c.get("surface") == "ladder_rung" and b.get(name, {}).get("state") == "planted"]
        rows.append({"step": [k + 1, (k + 1) % n + 1], "rise": float(np.mean(d)) if d else None, "spread": float(np.ptp(d)) if len(d) > 1 else 0.0})
    known = [r["rise"] for r in rows if r["rise"] is not None]
    return {"steps": rows, "rise_per_cycle": float(sum(known)), "mean_rise_per_frame": float(np.mean(known)) if known else 0.0}


def plan(ladder_height: float, rung_spacing: float, rungs_per_cycle: int = 2) -> dict:
    """How many loop cycles a ladder needs. Climbing ends with the hands on the top rung's level."""
    rungs = ladder_height / rung_spacing
    cycles = rungs / rungs_per_cycle
    whole = int(round(cycles))
    return {"rungs": round(rungs, 2), "cycles_exact": round(cycles, 2), "cycles": max(1, whole),
            "leftover_px": round((cycles - whole) * rungs_per_cycle * rung_spacing, 1),
            "fits": abs(cycles - whole) * rungs_per_cycle <= 0.25}   # within a quarter rung


def check(character, action, rungs=8, rise_per_cycle=None):
    """Put the action on a ladder of `rungs` rungs and check rung landing, using contact rise or an assumed rise."""
    act = A.load_action(character, action)
    doc = act.annotations or {}
    sc = doc["scene"]
    lad = next(p for p in sc["props"] if p["type"] == "ladder")
    spec_p = SPECS / f"{character}_ladder.json"
    s = json.loads(spec_p.read_text())["rung_spacing_px"] if spec_p.exists() else lad["rung_spacing"]   # same rungs as the redraw spec
    cr = contact_rise(act)
    used = rise_per_cycle if rise_per_cycle is not None else (cr["rise_per_cycle"] if abs(cr["rise_per_cycle"]) > 0.25 * s else 2 * s)
    source = "given" if rise_per_cycle is not None else ("from rung contacts" if abs(cr["rise_per_cycle"]) > 0.25 * s else
                                                         f"ASSUMED 2 rungs per cycle ({2 * s:.0f}px): the contacts rise only {cr['rise_per_cycle']:.1f}px per cycle")
    pl = plan(rungs * s, s, 2)
    n = len(act.frames)
    scene = json.loads(json.dumps(sc))
    lad2 = next(p for p in scene["props"] if p["type"] == "ladder")
    lad2["top_y"] = scene["floor_y"] - rungs * s
    lad2["rung_spacing"] = s; lad2["first_rung_y"] = scene["floor_y"]
    # centre the rails between his drawn hands and feet (cell -> world via the path start), half his height apart
    H = float(np.median([np.ptp(np.nonzero((f[..., 3] > A.ALPHA_T).any(axis=1))[0]) + 1 for f in act.frames]))
    xs = [float(c["x"]) for cs in act.contacts for c in (cs or {}).values()]
    mid = scene["path"]["from"][0] - scene["anchor"][0] + float(np.median(xs))
    lad2["x_left"], lad2["x_right"] = mid - 0.25 * H, mid + 0.25 * H
    scene["path"] = {"type": "vertical_loop", "from": scene["path"]["from"], "rise_per_frame": used / n, "cycles": pl["cycles"]}
    res = P.check_action(act, scene)
    per_frame_off = []
    for f in res["frames"]:
        off = [c for c in f["contacts"] if c["state"] == "planted" and (c["dist"] is None or c["dist"] > c.get("tol", P.TOL))]
        per_frame_off.append(len(off))
    feet_y = [min((float(c["y"]) for nm, c in (act.contacts[k] or {}).items() if nm.startswith("foot")), default=None) for k in range(n)]
    fy = [v for v in feet_y if v is not None]
    out = {"character": character, "action": action, "rung_spacing": s, "rungs": rungs, "plan": pl,
           "rise_per_cycle_used": round(used, 1), "rise_source": source, "contact_rise": cr,
           "frames_with_contacts_off_rungs": sum(1 for v in per_frame_off if v), "frames_checked": len(per_frame_off),
           "foot_height_range_in_cell": round(float(np.ptp(fy)), 1) if fy else None,
           "flags": res["flags"],
           "verdict": ("Feet stay at one cell height (range %.0f px < a rung %.0f px): planted feet cannot step up, so any rise slides them "
                       "off the rungs; the cycle needs redrawing (specs/guard_ladder.png)." % (np.ptp(fy), s)) if fy and np.ptp(fy) < 0.5 * s else
                      "Feet change height by at least half a rung."}
    od = A.output_dir(character, action)
    (od / "ladder.json").write_text(json.dumps({**out, "frames": res["frames"]}, indent=1), encoding="utf-8")
    P.scene_image(act, {**res, "frames": res["frames"][: 2 * n]}, cols=7,
                  title=f"{character}/{action} on a {rungs}-rung ladder: {pl['cycles']} cycle(s), rise {used:.0f}px per cycle ({source})").save(od / "ladder.png", optimize=True)
    return out


# ---------------------------------------------------------------- redraw spec (back view, diagonal limbs move together)

def ladder_spec(character="guard", frames=8):
    act = A.load_action(character, "ladder_up", use_annotations=False)
    H = float(np.median([np.ptp(np.nonzero((f[..., 3] > A.ALPHA_T).any(axis=1))[0]) + 1 for f in act.frames]))
    import intake
    cx = round(float(np.median([intake.head_x(f) for f in act.frames])), 1)
    ground = 535.0
    s = round(H / 6, 1)                  # rung spacing ~ a sixth of his height (~0.3 m for a ~1.7 m figure)
    rise = 2 * s / frames                # one rung per half cycle: the body rises s/4 per frame
    hand_dx, foot_dx = 0.17 * H, 0.09 * H
    hand_y0, foot_y0 = ground - 0.95 * H, ground          # top hand near the top of the head, a foot on the rung under him
    half_n = frames // 2
    top = {"hand_l": ground - 0.95 * H, "hand_r": ground - 0.95 * H, "foot_l": ground - s, "foot_r": ground - s}
    xs = {"hand_l": cx - hand_dx, "hand_r": cx + hand_dx, "foot_l": cx - foot_dx, "foot_r": cx + foot_dx}
    grips_first = {"hand_l", "foot_r"}          # first half: left hand + right foot grip, right hand + left foot move
    out = []
    for k in range(frames):
        half, j = divmod(k, half_n)
        u = j / half_n
        c = {}
        for name in xs:
            gripping = (name in grips_first) == (half == 0)
            if gripping:   # on a fixed rung while the body rises: moves DOWN one rung in the cell over the half cycle
                y, st = top[name] + u * s, "planted"
            else:          # moving up two rungs in the world = UP one rung in the cell
                y, st = top[name] + s - u * s, ("planted" if j == 0 else "free")
            c[name] = {"x": round(xs[name], 1), "y": round(y, 1), "state": st, "surface": "ladder_rung"}
        movers = "right hand + left foot" if half == 0 else "left hand + right foot"
        out.append({"frame": k + 1, "pose": f"{movers} move up ({j + 1}/{half_n})", "contacts": c, "hip_y": round(ground - 0.5 * H, 1)})
    spec = {"format": "workbench-spec/1", "kind": "ladder", "character": character, "action": "ladder_up", "replaces": f"{character}/ladder_up (rejected)",
            "cell_size": [640, 576], "ground_y": ground, "head_x": cx, "figure_height_px": round(H, 1), "rung_spacing_px": s,
            "rise_px_per_frame": round(rise, 2), "rise_px_per_cycle": round(2 * s, 1), "frames": out,
            "criteria": {"frame_count": frames, "rise_per_cycle_from_contacts": round(2 * s, 1), "rise_tolerance_px": round(0.15 * s, 1),
                         "foot_height_range_min_px": round(0.75 * s, 1),
                         "manual": ["back view: diagonal limbs move together (right hand with left foot, then left hand with right foot)",
                                    "grippers stay on their rung while the body rises; the cycle loops (frame 8 leads into frame 1 one rung higher)"]},
            "how": ("Draw %d frames, back view, on 640x576 cells. Rungs every %.0f px. In the first half the right hand and left foot each move up one "
                    "rung while the left hand and right foot grip (filled dots move DOWN %.1f px per frame in the cell as he rises); then swap. "
                    "Planted dots = gripping, rings = moving. The loop rises %.0f px per cycle (two rungs)." % (frames, s, rise, 2 * s))}
    SPECS.mkdir(exist_ok=True)
    (SPECS / f"{character}_ladder.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
    # sheet
    from diagnostics import BLUE, INK, RED, font, header, stack
    sc = 0.5; tw, th = 320, 288
    sheet = Image.new("RGB", (4 * tw, 2 * (th + 30)), (255, 255, 255)); d = ImageDraw.Draw(sheet)
    ghost = Image.fromarray(act.frames[0], "RGBA").resize((tw, th), Image.LANCZOS); ghost.putalpha(ghost.getchannel("A").point(lambda v: int(v * 0.16)))
    for k, fs in enumerate(out):
        x0, y0 = (k % 4) * tw, (k // 4) * (th + 30)
        sheet.paste(ghost, (x0, y0 + 30), ghost)
        # rungs drawn at the positions of this frame (they move down in the cell as he rises)
        first = foot_y0 + k * rise
        for r in range(-1, 8):
            ry = first - r * s
            if 0 < ry < 576:
                d.line([(x0 + (cx - 0.25 * H) * sc, y0 + 30 + ry * sc), (x0 + (cx + 0.25 * H) * sc, y0 + 30 + ry * sc)], fill=(150, 110, 60), width=2)
        for xr in (cx - 0.25 * H, cx + 0.25 * H):
            d.line([(x0 + xr * sc, y0 + 30), (x0 + xr * sc, y0 + 30 + th)], fill=(150, 110, 60), width=3)
        for name, c in fs["contacts"].items():
            px, py = x0 + c["x"] * sc, y0 + 30 + c["y"] * sc
            col = BLUE if name.endswith("_l") else RED
            if c["state"] == "planted": d.ellipse([px - 6, py - 6, px + 6, py + 6], fill=col, outline=INK)
            else: d.ellipse([px - 6, py - 6, px + 6, py + 6], outline=col, width=2)
            d.text((px - 16, py + 7), name, fill=col, font=font(9))
        d.text((x0 + 4, y0 + 4), f"{fs['frame']}: {fs['pose']}", fill=INK, font=font(11))
        d.rectangle([x0, y0, x0 + tw - 1, y0 + th + 29], outline=(225, 225, 225))
    hd = header(sheet.width, [f"{character} ladder climb redraw spec: {frames} frames, back view, two rungs per cycle",
                              spec["how"], "Brown = rungs and rails as they sit in this frame's cell. Faint = his current drawing (scale only). Blue = left, red = right."], 12)
    stack([hd, sheet]).save(SPECS / f"{character}_ladder.png", optimize=True)
    return spec


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("character"); c.add_argument("action"); c.add_argument("--rungs", type=int, default=8)
    c.add_argument("--rise", type=float, help="rise per cycle (cell px) instead of measuring it from the contacts")
    sub.add_parser("spec")
    a = p.parse_args(argv)
    if a.cmd == "check":
        o = check(a.character, a.action, a.rungs, a.rise)
        print(f"{a.rungs}-rung ladder ({o['rung_spacing']}px rungs): {o['plan']['cycles']} cycles; rise {o['rise_per_cycle_used']}px/cycle ({o['rise_source']})")
        print(f"contact rise per cycle: {o['contact_rise']['rise_per_cycle']:.1f}px; frames with contacts off rungs: {o['frames_with_contacts_off_rungs']}/{o['frames_checked']}")
        print(o["verdict"])
    else:
        s = ladder_spec(); print(f"specs/guard_ladder.json: rungs {s['rung_spacing_px']}px, rise {s['rise_px_per_frame']}px/frame")


if __name__ == "__main__":
    main()
