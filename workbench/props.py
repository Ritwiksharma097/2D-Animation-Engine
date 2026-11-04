"""Scene props (floor, ledge, ladder), an anchor path, and contact / clipping checks.

A scene lives in the action document under "scene" (FORMAT.md, "Scenes"). Units are the action's own
cell pixels, in a world where the frame's cell is placed so that its `anchor` point sits on the path.

    python workbench/props.py ren climb_up                 # check against the stored scene, write scene.png
    python workbench/props.py guard climb_up --fit ledge   # search ledge height / path for the guard
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ALPHA_T = 128
TOL = 6.0        # cell px: a planted contact within this of a surface counts as on it (~3 game px for Ren)
CLIP_TOL = 4.0   # cell px: pixels deeper than this inside a solid count as clipping
FOOT = ("foot", "toe", "heel")
HAND_ALLOW = 14.0   # cell px: pixels this close to a hand contact may overlap a solid (fingers curl over a cap)
FRONT_BAND = 40.0   # cell px behind a ledge's front face: a near limb drawn in front of the face, not inside it
HAND = ("hand", "palm", "finger")


# ---------------------------------------------------------------- geometry

def surfaces(scene: dict) -> list[dict]:
    """Segments a contact can rest on: {id, kind, a:(x,y), b:(x,y)}."""
    fy = scene["floor_y"]
    out, floor_gaps = [], []
    for p in scene.get("props", []):
        if p["type"] == "ledge":
            cap = p.get("cap", {"overhang": 0, "thickness": 0})
            fx, bx, ty = p["front_x"], p["back_x"], p["top_y"]
            out.append({"id": p["id"] + ".top", "kind": "ledge_top", "a": (fx, ty), "b": (bx, ty)})
            if cap["thickness"]:
                out.append({"id": p["id"] + ".cap_front", "kind": "ledge_face", "a": (fx, ty), "b": (fx, ty + cap["thickness"])})
                out.append({"id": p["id"] + ".cap_under", "kind": "ledge_face", "a": (fx, ty + cap["thickness"]), "b": (fx + cap["overhang"], ty + cap["thickness"])})
            out.append({"id": p["id"] + ".face", "kind": "ledge_face", "a": (fx + cap["overhang"], ty + cap["thickness"]), "b": (fx + cap["overhang"], fy)})
            floor_gaps.append((fx + cap["overhang"], bx - cap["overhang"]))
        elif p["type"] == "ladder":
            xl, xr, top, bottom = p["x_left"], p["x_right"], p["top_y"], p.get("bottom_y", fy)
            y = p["first_rung_y"]
            k = 0
            while y >= top - 1e-6:
                out.append({"id": f"{p['id']}.rung{k}", "kind": "ladder_rung", "a": (xl, y), "b": (xr, y)})
                y -= p["rung_spacing"]; k += 1
            for side, x in (("left", xl), ("right", xr)):
                out.append({"id": f"{p['id']}.rail_{side}", "kind": "ladder_rail", "a": (x, top), "b": (x, bottom)})
    # floor, minus the parts under ledge bodies
    xs = [-1e5] + [v for g in sorted(floor_gaps) for v in g] + [1e5]
    for x0, x1 in zip(xs[0::2], xs[1::2]):
        out.append({"id": "floor", "kind": "ground", "a": (x0, fy), "b": (x1, fy)})
    return out


def solids(scene: dict) -> list[tuple[float, float, float, float]]:
    """Axis-aligned boxes (x0, y0, x1, y1) the body must not enter. Ladders are behind the character."""
    fy = scene["floor_y"]
    out = [(-1e5, fy, 1e5, fy + 1e4)]
    for p in scene.get("props", []):
        if p["type"] == "ledge":
            cap = p.get("cap", {"overhang": 0, "thickness": 0})
            out.append((p["front_x"], p["top_y"], p["back_x"], p["top_y"] + cap["thickness"]))
            out.append((p["front_x"] + cap["overhang"], p["top_y"], p["back_x"] - cap["overhang"], fy))
    return out


def seg_dist(p, a, b) -> float:
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def nearest_surface(p, surfs, kind=None):
    best = None
    for s in surfs:
        if kind and s["kind"] != kind and s["id"] != kind:
            continue
        d = seg_dist(p, s["a"], s["b"])
        if best is None or d < best[0]:
            best = (d, s)
    return best


SURFACE_Y = {"ground": "floor_y"}


def target_y(scene: dict, surface: str | None) -> float | None:
    """World y of a horizontal surface kind (ground or the first ledge top)."""
    if surface == "ground":
        return scene["floor_y"]
    if surface == "ledge_top":
        tops = [p["top_y"] for p in scene.get("props", []) if p["type"] == "ledge"]
        return tops[0] if tops else None
    return None


def contact_path(scene: dict, contacts: list[dict], base: list[tuple[float, float]], images=None) -> tuple[list, list]:
    """Per-frame cell offsets with x from `base` and y chosen so planted contacts sit on their named surfaces.

    Frames with no planted contact on a horizontal surface keep the base y. Returns (offsets, notes)."""
    out, notes = [], []
    notes_shift = []
    # x: hold shared planted contacts fixed between consecutive frames; otherwise follow the base path's step
    xs = [base[0][0]]
    for k in range(1, len(base)):
        a_, b_ = contacts[k - 1] or {}, contacts[k] or {}
        d = [float(a_[n]["x"]) - float(c["x"]) for n, c in b_.items()
             if c.get("state") == "planted" and n in a_ and a_[n].get("state") == "planted" and a_[n].get("surface") == c.get("surface")]
        xs.append(xs[-1] + (float(np.mean(d)) if d else base[k][0] - base[k - 1][0]))
    # a contact planted on a ledge top must be over that top: shift (and keep the shift for later frames)
    ledges = [p for p in scene.get("props", []) if p["type"] == "ledge"]
    shift_x = 0.0
    for k in range(len(xs)):
        xs[k] += shift_x
        for c in (contacts[k] or {}).values():
            if c.get("state") != "planted" or not ledges:
                continue
            wx = xs[k] + float(c["x"])
            d = 0.0
            if c.get("surface") == "ledge_top":
                lo, hi = ledges[0]["front_x"] + TOL, ledges[0]["back_x"] - TOL
                if wx < lo or wx > hi:
                    d = (lo - wx) if wx < lo else (hi - wx)
            elif c.get("surface") == "ground" and ledges[0]["front_x"] - TOL < wx < ledges[0]["back_x"]:
                d = (ledges[0]["front_x"] - TOL) - wx      # the floor under a ledge is not a surface: step in front of it
            if d:
                xs[k] += d; shift_x += d
                notes_shift.append(f"frame {k + 1}: moved {d:+.0f}px to put {c.get('name', 'contact')} on its {c.get('surface')}")
    base = [(x, y) for x, (_, y) in zip(xs, base)]
    for k, (ox, oy) in enumerate(base):
        ds = [target_y(scene, c.get("surface")) - float(c["y"]) for c in (contacts[k] or {}).values()
              if c.get("state") == "planted" and target_y(scene, c.get("surface")) is not None]
        if ds:
            out.append((ox, float(np.mean(ds)))); notes.append(f"y from {len(ds)} planted contact(s), spread {np.ptp(ds):.0f}px")
        else:
            out.append((ox, oy)); notes.append("no planted contact on a horizontal surface: base path")
    # frames standing on the floor only: step clear of a ledge face the body would otherwise be inside
    if images is not None and ledges:
        L = ledges[0]; carry = 0.0
        for k in range(len(out)):
            ox, oy = out[k][0] + carry, out[k][1]
            planted = [c for c in (contacts[k] or {}).values() if c.get("state") == "planted"]
            if planted and all(c.get("surface") == "ground" for c in planted):
                ys, xs_ = np.nonzero(images[k][..., 3] > ALPHA_T)
                wx, wy = xs_ + ox, ys + oy
                inside = (wy > L["top_y"] + CLIP_TOL) & (wx > L["front_x"]) & (wx < L["back_x"])
                if inside.any():
                    d = -(float(wx[inside].max()) - L["front_x"] + 1)
                    carry += d; ox += d
                    notes.append(f"frame {k + 1}: stepped {d:+.0f}px clear of the ledge face (floor-only contacts)")
            out[k] = (ox, oy)
    return out, notes + notes_shift


def path_offsets(scene: dict, n: int, contacts: list[dict] | None = None, images=None) -> list[tuple[float, float]]:
    """Cell-origin position in the world for each played frame."""
    ax, ay = scene["anchor"]
    path = scene["path"]
    if path["type"] == "from_contacts":
        base = path_offsets({**scene, "path": path["base"]}, n)
        return contact_path(scene, contacts or [{}] * n, base, images)[0]
    if path["type"] == "line":
        (x0, y0), (x1, y1) = path["from"], path["to"]
        ts = path.get("t") or [k / max(n - 1, 1) for k in range(n)]
        pts = [(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t) for t in ts]
    elif path["type"] == "points":
        pts = [tuple(p) for p in path["points"]]
    elif path["type"] == "vertical_loop":   # ladders: rise per frame, repeated cycles
        x0, y0 = path["from"]
        pts = [(x0, y0 - path["rise_per_frame"] * k) for k in range(n * path.get("cycles", 1))]
    else:
        raise ValueError(f"unknown path type {path['type']}")
    return [(x - ax, y - ay) for x, y in pts]


# ---------------------------------------------------------------- checks

def inside_depth(xs, ys, box):
    x0, y0, x1, y1 = box
    inside = (xs > x0) & (xs < x1) & (ys > y0) & (ys < y1)
    depth = np.minimum.reduce([xs - x0, x1 - xs, ys - y0, y1 - ys])
    return inside, np.where(inside, depth, 0)


def allowed_overlap(wx, wy, scene, hands):
    """Masks of solid-overlap pixels treated as drawing conventions rather than clipping.

    fingers: within HAND_ALLOW of a hand contact. front: inside a ledge but within FRONT_BAND of its front face
    and below the top surface by more than CLIP_TOL (a limb in front of the face; sinking through the top
    away from the front still counts as clipping)."""
    fingers = np.zeros(len(wx), bool)
    for hx, hy in hands:
        fingers |= np.hypot(wx - hx, wy - hy) <= HAND_ALLOW
    front = np.zeros(len(wx), bool)
    for p in scene.get("props", []):
        if p["type"] == "ledge":
            front |= (wx >= p["front_x"]) & (wx <= p["front_x"] + FRONT_BAND) & (wy > p["top_y"] + CLIP_TOL)
    return fingers, front


def frame_checks(img: np.ndarray, off, scene, surfs, sols, contacts: dict | None):
    ys, xs = np.nonzero(img[..., 3] > ALPHA_T)
    wx, wy = xs + off[0], ys + off[1]
    clip_px, clip_depth = 0, 0.0
    clip_where = []
    hands = [(float(c["x"]) + off[0], float(c["y"]) + off[1]) for n, c in (contacts or {}).items() if n.split("_")[0] in HAND]
    fingers, front = allowed_overlap(wx, wy, scene, hands)
    allowed = {"fingers_px": 0, "in_front_of_face_px": 0}
    for box in sols:
        inside, depth = inside_depth(wx, wy, box)
        deep = depth > CLIP_TOL
        allowed["fingers_px"] += int((deep & fingers).sum())
        allowed["in_front_of_face_px"] += int((deep & front & ~fingers).sum())
        deep &= ~fingers & ~front
        if deep.any():
            clip_px += int(deep.sum()); clip_depth = max(clip_depth, float(depth.max()))
            clip_where.append([float(wx[deep].mean()), float(wy[deep].mean())])
    # support: opaque pixels within TOL outside a surface (touching it)
    touching = {}
    for s in surfs:
        if s["kind"] in ("ladder_rail",):
            continue
        (ax, ay), (bx, by) = s["a"], s["b"]
        if ay == by:   # horizontal: pixels just above it, within its x span
            m = (wy >= ay - TOL) & (wy <= ay + CLIP_TOL) & (wx >= min(ax, bx)) & (wx <= max(ax, bx))
        else:          # vertical face: pixels just in front of it
            m = (wx >= ax - TOL) & (wx <= ax + CLIP_TOL) & (wy >= min(ay, by)) & (wy <= max(ay, by))
        if m.any():
            touching[s["id"]] = int(m.sum())
    lowest = (float(wx[wy.argmax()]), float(wy.max())) if len(wy) else None
    out = {"offset": [float(off[0]), float(off[1])], "clip_px": clip_px, "clip_depth": round(clip_depth, 1),
           "clip_at": clip_where, "allowed_overlap": allowed, "touching": touching, "lowest": lowest, "contacts": []}
    for name, c in (contacts or {}).items():
        p = (float(c["x"]) + off[0], float(c["y"]) + off[1])
        want = c.get("surface")
        kind = want if want and want != "ground" else ("ground" if want == "ground" else None)
        near = nearest_surface(p, surfs, kind)
        anywhere = nearest_surface(p, surfs)
        pf, pfr = allowed_overlap(np.array([p[0]]), np.array([p[1]]), scene, [] if name.split("_")[0] not in HAND else [])
        is_hand = name.split("_")[0] in HAND
        tol = HAND_ALLOW if is_hand else TOL   # fingers drawn curling over an edge
        in_solid = (any(box[0] + CLIP_TOL < p[0] < box[2] - CLIP_TOL and box[1] + CLIP_TOL < p[1] < box[3] - CLIP_TOL for box in sols)
                    and not pfr[0] and not (is_hand and near and near[0] <= tol))
        out["contacts"].append({"name": name, "state": c.get("state"), "surface": want, "world": [round(p[0], 1), round(p[1], 1)],
                                "dist": round(near[0], 1) if near else None, "nearest": anywhere[1]["id"] if anywhere else None,
                                "nearest_dist": round(anywhere[0], 1) if anywhere else None, "in_solid": in_solid, "tol": tol})
    return out


def check_action(act, scene: dict) -> dict:
    n = len(act.frames)
    offs = path_offsets(scene, n, act.contacts, act.frames)
    surfs, sols = surfaces(scene), solids(scene)
    seq = [k % n for k in range(len(offs))]
    frames = []
    for k, off in zip(seq, offs):
        cs = act.contacts[k] if act.contacts else None
        frames.append({"frame": k + 1, "index": k, **frame_checks(act.frames[k], off, scene, surfs, sols, cs)})
    flags = []

    def flag(code, fr, msg):
        flags.append({"level": "suspect", "code": code, "frames": fr, "message": msg})

    area = float(np.median([(f[..., 3] > ALPHA_T).sum() for f in act.frames]))
    clips = [f for f in frames if f["clip_px"] > 0.002 * area]
    if clips:
        flag("body_clips_prop", [f["frame"] for f in clips], "Body is inside the ledge or floor by more than "
             f"{CLIP_TOL:.0f}px: " + ", ".join(f"{f['frame']}:{f['clip_px']}px deep {f['clip_depth']:.0f}" for f in clips) + ".")
    floating = [f for f in frames if not f["touching"]]
    if floating:
        flag("unsupported_body", [f["frame"] for f in floating], f"Nothing touches any surface (within {TOL:.0f}px): frames "
             + ", ".join(str(f["frame"]) for f in floating) + ".")
    for f in frames:
        for c in f["contacts"]:
            if c["state"] != "planted":
                if c["in_solid"]:
                    flag("contact_in_prop", [f["frame"]], f"Frame {f['frame']}: {c['name']} (free) is inside a solid.")
                continue
            if c["dist"] is None or c["dist"] > c.get("tol", TOL):
                part = c["name"].split("_")[0]
                what = "reaching into air" if part in HAND else ("pushing off nothing" if part in FOOT else "not on a surface")
                flag("contact_off_surface", [f["frame"]], f"Frame {f['frame']}: planted {c['name']} is {what}: "
                     f"{c['dist'] if c['dist'] is not None else '?'}px from {c['surface'] or 'any surface'} "
                     f"(nearest {c['nearest']} at {c['nearest_dist']}px).")
            if c["in_solid"]:
                flag("contact_in_prop", [f["frame"]], f"Frame {f['frame']}: planted {c['name']} is inside a solid.")
    slides = []
    for a, b in zip(frames, frames[1:]):
        ca = {c["name"]: c for c in a["contacts"] if c["state"] == "planted"}
        for c in b["contacts"]:
            if c["state"] == "planted" and c["name"] in ca and c["surface"] == ca[c["name"]]["surface"]:
                dx = c["world"][0] - ca[c["name"]]["world"][0]
                slides.append({"from": a["frame"], "to": b["frame"], "name": c["name"], "dx": round(dx, 1)})
    big = [s for s in slides if abs(s["dx"]) > TOL]
    if big:
        flag("planted_contact_slides", sorted({s["to"] for s in big}), "Planted contacts move along their surface between frames: "
             + ", ".join(f"{s['name']} {s['from']}->{s['to']} {s['dx']:+.0f}px" for s in big) + ".")
    return {"scene": scene, "frames": frames, "flags": flags, "contact_slides": slides,
            "limits": [f"Support = any opaque pixel within {TOL:.0f}px outside a surface; it does not know which body part it is.",
                       f"Clipping counts pixels more than {CLIP_TOL:.0f}px inside a solid; a drawn shadow or loose cloth counts too.",
                       "The path is what was supplied (or fitted); a different path changes every result.",
                       "Ladders are treated as behind the character, so the body overlapping a ladder is never clipping.",
                       f"Allowed as drawing conventions (counted in allowed_overlap, not as clipping): pixels within {HAND_ALLOW:.0f}px of a hand "
                       f"contact (fingers over a cap), and pixels within {FRONT_BAND:.0f}px behind a ledge's front face below its top (a near limb "
                       "drawn in front of the face). Sinking through the top further back still counts."]}


# ---------------------------------------------------------------- fitting

def fit_ledge(act, floor_y=None, heights=None, dxs=None, fronts=None):
    """Grid search: ledge top height, horizontal travel and front edge for a straight floor-to-top path.

    The path starts with frame 1's lowest pixel on the floor and ends with the last frame's lowest pixel on
    the ledge top. Cost = clipping pixels / figure area + 1 per frame touching nothing. A heuristic, not truth.
    """
    n = len(act.frames)
    lows = [int(np.nonzero((f[..., 3] > ALPHA_T).any(axis=1))[0].max()) for f in act.frames]
    cx = act.frames[0].shape[1] / 2
    H = float(np.median([np.ptp(np.nonzero((f[..., 3] > ALPHA_T).any(axis=1))[0]) for f in act.frames]))
    floor_y = floor_y or 1000.0
    heights = heights if heights is not None else np.arange(0.1, 0.81, 0.05) * H
    dxs = dxs if dxs is not None else np.arange(0, 0.81, 0.1) * H
    area = float(np.median([(f[..., 3] > ALPHA_T).sum() for f in act.frames]))
    best, table = None, []
    for h in heights:
        for dx in dxs:
            front_range = fronts if fronts is not None else np.arange(-0.1, 0.51, 0.05) * H
            for fr in front_range:
                x0 = 1000.0
                scene = {"floor_y": floor_y, "anchor": [cx, lows[0]],
                         "path": {"type": "line", "from": [x0, floor_y], "to": [x0 + dx, floor_y - h - (lows[-1] - lows[0])]},
                         "props": [{"type": "ledge", "id": "ledge", "front_x": x0 + fr, "back_x": x0 + fr + 2 * H,
                                    "top_y": floor_y - h, "cap": {"overhang": 0, "thickness": 0}}]}
                res = check_action(act, scene)
                clip = sum(f["clip_px"] for f in res["frames"]) / area
                floating = sum(1 for f in res["frames"] if not f["touching"])
                # the last frame must stand on the top and in front of nothing: require it over the ledge
                last_x = res["frames"][-1]["lowest"][0] if res["frames"][-1]["lowest"] else 0
                off_top = 0 if last_x >= x0 + fr else 1
                cost = clip + floating + 3 * off_top
                table.append({"height": float(h), "dx": float(dx), "front": float(fr), "clip": round(clip, 3),
                              "floating": floating, "cost": round(cost, 3)})
                if best is None or cost < best[0]:
                    best = (cost, scene, res)
    return {"figure_height": H, "best": best[1], "best_result": best[2], "best_cost": best[0], "table": table}


# ---------------------------------------------------------------- image

def scene_image(act, result, cols=7, panel_w=300, title=""):
    """One panel per frame: the frame at its path position over the props, contacts and problems marked."""
    scene = result["scene"]
    n = len(result["frames"])
    surfs, sols = surfaces(scene), solids(scene)
    # world crop covering every placed frame
    h, w = act.frames[0].shape[:2]
    offs = [f["offset"] for f in result["frames"]]
    X0 = min(o[0] for o in offs) - 20; X1 = max(o[0] for o in offs) + w + 20
    Y0 = min(o[1] for o in offs) - 20; Y1 = scene["floor_y"] + 40
    sc = panel_w / (X1 - X0)
    ph = int((Y1 - Y0) * sc)
    rows = (n + cols - 1) // cols
    from diagnostics import font, header, stack, AQUA, RED, ORANGE, INK, MUTED
    sheet = Image.new("RGB", (cols * panel_w, rows * (ph + 30)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    W = lambda x, y, px, py: (px + (x - X0) * sc, py + 26 + (y - Y0) * sc)
    for k, fr in enumerate(result["frames"]):
        px, py = (k % cols) * panel_w, (k // cols) * (ph + 30)
        for box in sols:
            a = W(max(box[0], X0), max(box[1], Y0), px, py); b = W(min(box[2], X1), min(box[3], Y1), px, py)
            if a[0] < b[0] and a[1] < b[1]:
                d.rectangle([a, b], fill=(214, 204, 186), outline=(150, 135, 110))
        for s in surfs:
            if s["kind"] in ("ladder_rung", "ladder_rail"):
                a, b = W(*s["a"], px, py), W(*s["b"], px, py)
                d.line([a, b], fill=(120, 90, 50), width=3 if s["kind"] == "ladder_rail" else 2)
        img = Image.fromarray(act.frames[(fr["frame"] - 1)], "RGBA")
        tw, th = max(1, int(w * sc)), max(1, int(h * sc))
        t = img.resize((tw, th), Image.LANCZOS)
        ox, oy = W(fr["offset"][0], fr["offset"][1], px, py)
        sheet.paste(t, (int(ox), int(oy)), t)
        if fr["clip_px"]:
            for cxy in fr["clip_at"]:
                q = W(*cxy, px, py); d.ellipse([q[0] - 6, q[1] - 6, q[0] + 6, q[1] + 6], outline=RED, width=3)
        for c in fr["contacts"]:
            q = W(*c["world"], px, py); r = 5
            ok = c["dist"] is not None and c["dist"] <= c.get("tol", TOL)
            if c["state"] == "planted":
                d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=AQUA if ok else RED, outline=INK)
            else:
                d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], outline=ORANGE, width=2)
        label = f"{k + 1}: frame {fr['frame']}"
        bad = [c["name"] for c in fr["contacts"] if c["state"] == "planted" and (c["dist"] is None or c["dist"] > c.get("tol", TOL))]
        if fr["clip_px"]:
            label += f"  CLIP {fr['clip_px']}px"
        if not fr["touching"]:
            label += "  FLOATING"
        if bad:
            label += "  off: " + ",".join(bad)
        d.text((px + 4, py + 4), label, fill=RED if ("CLIP" in label or "FLOAT" in label or bad) else INK, font=font(12))
        d.rectangle([px, py, px + panel_w - 1, py + ph + 29], outline=(225, 225, 225))
    hd = header(sheet.width, [title or f"{act.character}/{act.action} - scene check",
                              "Tan = ledge/floor solids, brown lines = ladder. Green dot = planted contact on a surface, red dot = planted contact "
                              f"off every surface (> {TOL:.0f}px), orange ring = free contact, red circle = body clipping into a solid."], 13)
    return stack([hd, sheet])


# ---------------------------------------------------------------- CLI

def main(argv=None):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import analyze
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("character"); p.add_argument("action")
    p.add_argument("--fit", choices=["ledge"], help="search ledge height/path instead of using the stored scene")
    p.add_argument("--no-annotations", action="store_true")
    p.add_argument("--path", choices=["stored", "contacts"], default="stored",
                   help="contacts = keep the stored path's x but take y from planted contacts (scene_contacts.png)")
    a = p.parse_args(argv)
    act = analyze.load_action(a.character, a.action, use_annotations=not a.no_annotations)
    od = analyze.output_dir(a.character, a.action)
    if a.fit:
        fit = fit_ledge(act)
        res = fit["best_result"]
        b = fit["best"]
        h = b["floor_y"] - b["props"][0]["top_y"]
        print(f"best fit: ledge {h:.0f}px high ({h / fit['figure_height']:.2f} x figure height), front edge "
              f"{b['props'][0]['front_x'] - b['path']['from'][0]:+.0f}px from start, path dx {b['path']['to'][0] - b['path']['from'][0]:.0f}px; cost {fit['best_cost']:.2f}")
        (od / "scene_fit.json").write_text(json.dumps({k: v for k, v in fit.items() if k != "best_result"}, indent=1), encoding="utf-8")
        name = "scene_fit.png"
    else:
        scene = (act.annotations or {}).get("scene")
        if not scene:
            p.error("no scene in the annotations document; add one or use --fit ledge")
        name = "scene.png"
        if a.path == "contacts":
            scene = {**scene, "path": {"type": "from_contacts", "base": scene["path"]}}
            name = "scene_contacts.png"
            base = path_offsets({**scene, "path": scene["path"]["base"]}, len(act.frames))
            offs, notes = contact_path(scene, act.contacts or [{}] * len(act.frames), base)
            print("  frame: contact-derived y offset minus stored path y (negative = drawing wants to be higher)")
            for k, ((_, y0), (_, y1), nt) in enumerate(zip(base, offs, notes)):
                print(f"   {k + 1:2d}: {y1 - y0:+7.1f}px  ({nt})")
        res = check_action(act, scene)
    res["surfaces"], res["solids"] = surfaces(res["scene"]), solids(res["scene"])
    (od / name.replace(".png", "_check.json")).write_text(json.dumps(res, indent=1), encoding="utf-8")
    scene_image(act, res).save(od / name, optimize=True)
    for f in res["flags"]:
        print(" ", f["code"], f["message"])
    if not res["flags"]:
        print("  no scene flags (not a pass: see limits)")
    print("  ->", (od / name).relative_to(ROOT))


if __name__ == "__main__":
    main()
