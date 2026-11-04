"""Art intake: a generated sheet or a folder of frames -> an action in incoming/<character>/<action>/ (never assets/).

    python workbench/intake.py sheet.png --character guard --action walk_v2 --replaces walk --spec specs/guard_walk.json
    python workbench/intake.py frames_folder --character ren --action walk_8 --replaces walk_keypose
    python workbench/intake.py sheet.png --character ren --action test --grid 7x2

Steps: find figures (a --grid, or connected components with small detached pieces such as effects or props
attached to the nearest figure), scale them uniformly to the height of the action they replace (or the
character's identity reference), align each frame like the existing assets (head centre and lowest pixel;
see manifest conventions), write NN.png + intake.json, analyse, and run spec_check if --spec is given.
The review page lists it as "new, awaiting owner" next to the action it would replace.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze as A  # noqa: E402

INCOMING = A.ROOT / "incoming"
ALPHA_T = A.ALPHA_T


# ---------------------------------------------------------------- input -> RGBA with a usable alpha

def to_rgba(img: Image.Image, bg_tol: float = 30.0) -> np.ndarray:
    """RGBA array. Images without real transparency get their background keyed out from the border colour."""
    a = np.array(img.convert("RGBA"))
    if (a[..., 3] < 250).mean() > 0.01:
        return a
    border = np.concatenate([a[0, :, :3], a[-1, :, :3], a[:, 0, :3], a[:, -1, :3]]).astype(np.float32)
    bg = np.median(border, axis=0)
    dist = np.linalg.norm(a[..., :3].astype(np.float32) - bg, axis=2)
    alpha = np.clip((dist - bg_tol * 0.5) / (bg_tol * 0.5) * 255, 0, 255).astype(np.uint8)  # soft edge over the tolerance
    a[..., 3] = alpha
    return a


# ---------------------------------------------------------------- finding figures

def split_grid(a: np.ndarray, cols: int, rows: int) -> list[np.ndarray]:
    h, w = a.shape[:2]
    out = []
    for r in range(rows):
        for c in range(cols):
            cell = a[r * h // rows:(r + 1) * h // rows, c * w // cols:(c + 1) * w // cols]
            if (cell[..., 3] > ALPHA_T).sum() > 50:
                out.append(cell)
    return out


def split_components(a: np.ndarray, min_main=0.2, speck=30) -> list[np.ndarray]:
    """Main figures = components >= min_main x the largest; smaller pieces join the nearest main figure."""
    m = (a[..., 3] > ALPHA_T).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    comps = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= speck]
    if not comps:
        return []
    biggest = max(st[i, cv2.CC_STAT_AREA] for i in comps)
    mains = [i for i in comps if st[i, cv2.CC_STAT_AREA] >= min_main * biggest]
    groups = {i: [i] for i in mains}

    def box(i):
        x, y, w, h = st[i, 0], st[i, 1], st[i, 2], st[i, 3]
        return x, y, x + w, y + h

    for i in comps:
        if i in groups:
            continue
        x0, y0, x1, y1 = box(i)
        best, bd = None, 1e18
        for j in mains:
            X0, Y0, X1, Y1 = box(j)
            dx = max(0, X0 - x1, x0 - X1); dy = max(0, Y0 - y1, y0 - Y1)
            d = dx * dx + dy * dy
            if d < bd:
                best, bd = j, d
        groups[best].append(i)
    figs = []
    for j, members in groups.items():
        sel = np.isin(lab, members)
        ys, xs = np.nonzero(sel)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        crop = a[y0:y1, x0:x1].copy()
        crop[~sel[y0:y1, x0:x1], 3] = 0       # drop pixels of other figures overlapping the box
        figs.append((x0, y0, x1, y1, crop))
    # reading order: rows (by vertical centre, tolerance half a median height), then left to right
    hmed = np.median([f[3] - f[1] for f in figs])
    figs.sort(key=lambda f: ((f[1] + f[3]) / 2, f[0]))
    rows, cur = [], [figs[0]]
    for f in figs[1:]:
        if abs((f[1] + f[3]) / 2 - (cur[0][1] + cur[0][3]) / 2) < 0.5 * hmed:
            cur.append(f)
        else:
            rows.append(cur); cur = [f]
    rows.append(cur)
    return [f[4] for r in rows for f in sorted(r, key=lambda f: f[0])]


def load_source(src: Path, grid: str | None) -> list[np.ndarray]:
    if src.is_dir():
        files = sorted(p for p in src.iterdir() if p.suffix.lower() in (".png", ".webp", ".jpg", ".jpeg"))
        return [to_rgba(Image.open(f)) for f in files]
    a = to_rgba(Image.open(src))
    if grid:
        c, r = (int(v) for v in grid.lower().split("x"))
        return split_grid(a, c, r)
    return split_components(a)


# ---------------------------------------------------------------- scale + align

def trim(a):
    ys, xs = np.nonzero(a[..., 3] > ALPHA_T)
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else a


def head_x(a, frac=0.34):
    """Median x of opaque pixels in the top ~third: the manifest's alignment convention."""
    m = a[..., 3] > ALPHA_T
    ys, xs = np.nonzero(m)
    top, h = ys.min(), ys.max() - ys.min() + 1
    sel = ys < top + frac * h
    return float(np.median(xs[sel]))


def target_geometry(character, replaces):
    """Reference height, cell, ground y and head x the new frames are fitted to."""
    man = A.load_manifest()
    ch = man["characters"][character]
    if replaces:
        act = A.load_action(character, replaces, use_annotations=False)
        frames = act.frames
        src = f"{character}/{replaces}"
        ground = act.ground_y
    else:
        frames = [A.load_rgba(A.ASSETS / ch["identity_reference"])]
        src = ch["identity_reference"]
        ground = man["conventions"]["ground_y"]
    hs = [np.ptp(np.nonzero((f[..., 3] > ALPHA_T).any(axis=1))[0]) + 1 for f in frames]
    hx = [head_x(f) for f in frames]
    return {"height": float(np.median(hs)), "cell": [frames[0].shape[1], frames[0].shape[0]], "ground_y": float(ground),
            "head_x": float(np.median(hx)), "from": src}


def place(fig: np.ndarray, scale: float, cell, ground_y: float, hx: float):
    t = trim(fig)
    if abs(scale - 1) > 1e-6:
        im = Image.fromarray(t, "RGBA")
        t = np.array(im.resize((max(1, round(t.shape[1] * scale)), max(1, round(t.shape[0] * scale))), Image.LANCZOS))
    W, H = cell
    out = np.zeros((H, W, 4), np.uint8)
    ox = int(round(hx - head_x(t)))
    oy = int(round(ground_y - (np.nonzero((t[..., 3] > ALPHA_T).any(axis=1))[0].max())))
    ys0, xs0 = max(0, oy), max(0, ox)
    ys1, xs1 = min(H, oy + t.shape[0]), min(W, ox + t.shape[1])
    if ys1 > ys0 and xs1 > xs0:
        out[ys0:ys1, xs0:xs1] = t[ys0 - oy:ys1 - oy, xs0 - ox:xs1 - ox]
    clipped = not (oy >= 0 and ox >= 0 and oy + t.shape[0] <= H and ox + t.shape[1] <= W)
    return out, {"offset": [ox, oy], "size": [int(t.shape[1]), int(t.shape[0])], "clipped_by_cell": bool(clipped)}


# ---------------------------------------------------------------- the command

def intake(src, character, action, replaces=None, grid=None, spec=None, height_scale=None, images=True):
    figs = load_source(Path(src), grid)
    if not figs:
        raise SystemExit("no figures found")
    tg = target_geometry(character, replaces)
    if spec:
        sp = json.loads(Path(spec).read_text(encoding="utf-8"))
        if sp.get("head_x"):
            tg["head_x"] = float(sp["head_x"]); tg["from"] += f" (head x {sp['head_x']} from the spec)"
    heights = [trim(f).shape[0] for f in figs]
    scale = height_scale or tg["height"] / float(np.median(heights))
    dest = INCOMING / character / action
    if dest.exists():
        for old in dest.glob("*.png"):
            old.unlink()
    dest.mkdir(parents=True, exist_ok=True)
    reg_frames = []
    for k, fig in enumerate(figs):
        out, info = place(fig, scale, tg["cell"], tg["ground_y"], tg["head_x"])
        name = f"{k + 1:02d}.png"
        Image.fromarray(out, "RGBA").save(dest / name)
        reg_frames.append({"file": name, **info})
    reg = {"format": "workbench-intake/1", "character": character, "action": action, "status": "new, awaiting owner",
           "source": str(src), "method": f"grid {grid}" if grid else ("folder" if Path(src).is_dir() else "connected components"),
           "replaces": f"{character}/{replaces}" if replaces else None, "spec": spec,
           "fitted_to": tg, "scale": round(scale, 4), "frames": reg_frames,
           "created": datetime.now().isoformat(timespec="seconds"),
           "alignment": "head centre (median x of the top third) at the target's head x; lowest pixel on ground_y; uniform scale to the target's median height"}
    (dest / "intake.json").write_text(json.dumps(reg, indent=1), encoding="utf-8")
    report = analyse(dest, reg, images)
    return reg, report


def incoming_action(dest: Path, reg: dict) -> A.Action:
    man = A.load_manifest()
    ch = man["characters"][reg["character"]]
    files = sorted(dest.glob("[0-9][0-9].png"))
    ref = ch.get("identity_reference")
    return A.Action(character=reg["character"], action=f"incoming_{reg['action']}", files=files,
                    frames=[A.load_rgba(f) for f in files], durations_ms=[1000 / 12] * len(files), loop_mode="loop",
                    ground_y=reg["fitted_to"]["ground_y"], is_walk="walk" in reg["action"] or "walk" in (reg.get("replaces") or ""),
                    game_scale=ch.get("game_scale_in_old_demos"), reference=A.load_rgba(A.ASSETS / ref) if ref else None,
                    reference_path=ref)


def analyse(dest: Path, reg: dict, images=True) -> dict:
    act = incoming_action(dest, reg)
    rep = A.analyze(act)
    rep["intake"] = {"status": reg["status"], "replaces": reg["replaces"]}
    od = A.OUT / "incoming" / reg["character"] / reg["action"]
    od.mkdir(parents=True, exist_ok=True)
    if reg.get("spec"):
        import spec_check as SC
        spec = json.loads(Path(reg["spec"]).read_text(encoding="utf-8"))
        travel = spec.get("old_travel_px_per_frame") or spec["travel_px_per_frame"]
        sact = SC.load_folder(dest, spec, travel)
        res = SC.evaluate(spec, sact, A.analyze(sact))
        rep["spec_check"] = {"spec": reg["spec"], "criteria": res, "meets_all_measurable": all(r["meets"] for r in res)}
    if images:
        import diagnostics
        rep["images"] = diagnostics.write_all(act, rep, od)
    (od / "report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return rep


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", help="a sheet image or a folder of frames")
    p.add_argument("--character", required=True); p.add_argument("--action", required=True)
    p.add_argument("--replaces", help="existing action this would replace (sets target height/cell/alignment)")
    p.add_argument("--grid", help="COLSxROWS to split a sheet by grid instead of connected components")
    p.add_argument("--spec", help="spec JSON to check against (see specs/)")
    p.add_argument("--scale", type=float, help="force a scale instead of fitting the height")
    p.add_argument("--no-images", action="store_true")
    a = p.parse_args(argv)
    reg, rep = intake(a.source, a.character, a.action, a.replaces, a.grid, a.spec, a.scale, not a.no_images)
    print(f"{len(reg['frames'])} frames -> incoming/{a.character}/{a.action}/ (scale {reg['scale']}, fitted to {reg['fitted_to']['from']})")
    print(rep["summary"])
    if "spec_check" in rep:
        sc = rep["spec_check"]
        print("spec:", "meets all measurable criteria" if sc["meets_all_measurable"] else "misses: " +
              ", ".join(r["criterion"] for r in sc["criteria"] if not r["meets"]))
    print("listed on the review page as 'new, awaiting owner'")


if __name__ == "__main__":
    main()
