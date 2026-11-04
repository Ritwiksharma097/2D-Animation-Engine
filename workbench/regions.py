"""Per-region identity check: hood, hair, face, tabard, armour... compared with the identity reference.

Regions are seeded by points on the character's identity reference, stored in
annotations/<character>/_identity.json (FORMAT.md, "Identity regions"):

    python workbench/regions.py init ren                         # write default seeds (cloud assistant's picks)
    python workbench/regions.py seed ren hood 319 142            # set / move one seed (reference image px)
    python workbench/regions.py compare ren walk_keypose jump rejected_walk_fourteen rejected_walk_flatboy

A region is the reference's connected patch of pixels near the seed colour. Its colour and its vertical
band (fraction of figure height, with a margin) are learned from the reference. In a frame, the region is
every opaque pixel within the colour tolerance inside that band.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze as A  # noqa: E402

COLOUR_TOL = 14.0   # Lab distance from the region colour for a pixel to belong to it
BAND_MARGIN = 0.06  # extra vertical band, as a fraction of figure height
TH_DE = 6.0         # region mean colour differs from the reference by more than this
TH_AREA = (0.6, 1.6)  # region share of the figure outside this ratio of the reference's

DEFAULT_SEEDS = {   # picked by eye on a gridded view of each identity reference (reference image px)
    "ren": {"hood": [319, 142], "hair": [392, 142], "face": [369, 199], "tunic": [319, 272], "sleeves": [296, 299],
            "satchel": [269, 341], "trousers": [319, 417], "boots": [311, 521]},
    "guard": {"helmet": [698, 179], "armour": [587, 438], "tabard": [754, 753], "face": [745, 308],
              "moustache": [800, 308], "gloves": [606, 772]},
}


def lab(img: np.ndarray) -> np.ndarray:
    l = cv2.cvtColor(img[..., :3].astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    l[..., 0] *= 100 / 255.0
    l[..., 1:] -= 128
    return l


def path_for(character):
    return A.ANNOTATIONS / character / "_identity.json"


def load_seeds(character):
    p = path_for(character)
    return json.loads(p.read_text(encoding="utf-8"))["regions"] if p.exists() else None


def save_seeds(character, regions):
    p = path_for(character)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"format": "workbench-identity/1", "character": character,
                             "reference": A.load_manifest()["characters"][character]["identity_reference"],
                             "note": "Seeds are reference-image pixels. Regions learn colour and vertical band from the reference.",
                             "regions": regions}, indent=1), encoding="utf-8")
    return p


def figure_box(mask):
    ys, xs = np.nonzero(mask)
    return int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())


def learn(ref: np.ndarray, seeds: dict) -> dict:
    """Region models from the reference: colour (Lab mean of the seed patch) and vertical band."""
    m = ref[..., 3] > A.ALPHA_T
    L = lab(ref)
    top, bot, _, _ = figure_box(m)
    h = bot - top + 1
    out = {}
    for name, s in seeds.items():
        x, y = s["seed"] if isinstance(s, dict) else s
        c = L[y - 3:y + 4, x - 3:x + 4].reshape(-1, 3).mean(0)
        near = (np.linalg.norm(L - c, axis=2) < COLOUR_TOL) & m
        n, lab_img = cv2.connectedComponents(near.astype(np.uint8), connectivity=8)
        comp = lab_img == lab_img[y, x] if near[y, x] else near & (np.hypot(*np.mgrid[:m.shape[0], :m.shape[1]][::-1] - np.array([x, y])[:, None, None]) < 15)
        ys = np.nonzero(comp)[0]
        f0, f1 = (ys.min() - top) / h, (ys.max() - top) / h
        out[name] = {"seed": [int(x), int(y)], "lab": c.tolist(),
                     "band": [max(0.0, f0 - BAND_MARGIN), min(1.0, f1 + BAND_MARGIN)]}
    # reference share and mean colour use exactly the frame definition, so the reference scores 1.00 / 0.0
    ref_meas = measure(ref, {k: {**v, "ref_share": 1.0, "ref_mean_lab": v["lab"]} for k, v in out.items()})
    for name, r in ref_meas.items():
        out[name]["ref_share"] = r["share"]
        out[name]["ref_mean_lab"] = L[r["mask"]].mean(0).tolist() if r["mask"].any() else out[name]["lab"]
    return out


def measure(frame: np.ndarray, model: dict) -> dict:
    m = frame[..., 3] > A.ALPHA_T
    L = lab(frame)
    top, bot, _, _ = figure_box(m)
    h = bot - top + 1
    rows = (np.arange(m.shape[0]) - top) / h
    out = {}
    for name, r in model.items():
        band = (rows >= r["band"][0]) & (rows <= r["band"][1])
        reg = m & band[:, None] & (np.linalg.norm(L - np.array(r["lab"]), axis=2) < COLOUR_TOL)
        share = float(reg.sum() / m.sum())
        mean = L[reg].mean(0) if reg.any() else None
        out[name] = {"share": share, "share_ratio": share / r["ref_share"] if r["ref_share"] else None,
                     "de": float(np.linalg.norm(mean - np.array(r["ref_mean_lab"]))) if mean is not None else None,
                     "mask": reg}
    return out


def action_regions(act, model):
    per = [measure(f, model) for f in act.frames]
    summary, flags = {}, []
    for name in model:
        ratios = [p[name]["share_ratio"] for p in per if p[name]["share_ratio"] is not None]
        des = [p[name]["de"] for p in per if p[name]["de"] is not None]
        s = {"share_ratio_median": float(np.median(ratios)) if ratios else None,
             "share_ratio_range": [float(min(ratios)), float(max(ratios))] if ratios else None,
             "de_median": float(np.median(des)) if des else None,
             "missing_frames": [i + 1 for i, p in enumerate(per) if p[name]["share"] < 0.1 * model[name]["ref_share"]]}
        summary[name] = s
        if s["share_ratio_median"] is not None and not TH_AREA[0] <= s["share_ratio_median"] <= TH_AREA[1]:
            flags.append({"level": "suspect", "code": "region_size_drift", "region": name, "frames": [],
                          "message": f"{name}: {s['share_ratio_median']:.2f}x the reference's share of the figure (median over frames)."})
        if s["de_median"] is not None and s["de_median"] > TH_DE:
            flags.append({"level": "suspect", "code": "region_colour_drift", "region": name, "frames": [],
                          "message": f"{name}: mean colour {s['de_median']:.1f} Lab units from the reference."})
        if len(s["missing_frames"]) > len(per) / 2:
            flags.append({"level": "suspect", "code": "region_missing", "region": name, "frames": s["missing_frames"],
                          "message": f"{name}: under 10% of its reference size in {len(s['missing_frames'])}/{len(per)} frames (gone, recoloured, or posed outside its band)."})
    return per, summary, flags


LIMITS = ("Regions are colour + vertical band learned from one reference pose. A crouch, jump or climb moves "
          "parts out of their band, so size changes there may be pose, not identity. Regions with similar colours "
          "(hood vs tunic, hair vs satchel) are separated only by the band. Shape changes inside a region "
          "(hood point, face) are not measured.")


def region_model(character):
    seeds = load_seeds(character)
    if not seeds:
        return None
    ref_rel = A.load_manifest()["characters"][character]["identity_reference"]
    return learn(A.load_rgba(A.ASSETS / ref_rel), seeds)


# ---------------------------------------------------------------- image

PALETTE = [(42, 120, 214), (235, 104, 52), (27, 175, 122), (237, 161, 0), (232, 123, 164), (0, 131, 0), (120, 80, 200), (200, 30, 40)]


def overlay(frame, masks, names, h=260):
    m = frame[..., 3] > A.ALPHA_T
    top, bot, x0, x1 = figure_box(m)
    base = frame.copy()
    base[..., :3] = (base[..., :3] * 0.35 + 255 * 0.65).astype(np.uint8)
    for k, n in enumerate(names):
        base[masks[n], :3] = PALETTE[k % len(PALETTE)]
    im = Image.fromarray(base[max(0, top - 5):bot + 5, max(0, x0 - 5):x1 + 5], "RGBA")
    k = h / im.height
    out = Image.new("RGB", (int(im.width * k), h), (255, 255, 255))
    t = im.resize(out.size, Image.LANCZOS)
    out.paste(t, (0, 0), t)
    return out


def compare_image(character, results, model, path):
    from diagnostics import font, header, stack
    names = list(model)
    ref = A.load_rgba(A.ASSETS / A.load_manifest()["characters"][character]["identity_reference"])
    tiles = [("reference", overlay(ref, {n: v["mask"] for n, v in measure(ref, model).items()}, names))]
    for action, (act, per, summary, flags) in results.items():
        k = int(np.argmax([sum(p[n]["share"] for n in names) for p in per]))  # most-covered frame
        tiles.append((f"{action} (frame {k + 1})", overlay(act.frames[k], {n: per[k][n]["mask"] for n in names}, names)))
    W = sum(t.width for _, t in tiles) + 10 * len(tiles)
    strip = Image.new("RGB", (max(W, 900), 295), (255, 255, 255))
    d = ImageDraw.Draw(strip)
    x = 0
    for lbl, t in tiles:
        strip.paste(t, (x, 30))
        for j, part in enumerate([lbl[:max(4, t.width // 7)], lbl[max(4, t.width // 7):][:max(4, t.width // 7)]]):
            d.text((x + 2, 2 + 13 * j), part, fill=(30, 30, 30), font=font(11))
        x += t.width + 10
    # table: share ratio and colour distance per region per action
    rows_h = 22
    tab = Image.new("RGB", (max(W, 900), 30 + rows_h * (len(names) + 1)), (255, 255, 255))
    td = ImageDraw.Draw(tab)
    td.text((6, 6), "region", fill=(30, 30, 30), font=font(12))
    cw = max(120, (max(W, 900) - 140) // max(1, len(results)))
    for j, action in enumerate(results):
        td.text((130 + j * cw, 6), action[:cw // 7], fill=(30, 30, 30), font=font(11))
    for i, n in enumerate(names):
        y = 28 + i * rows_h
        td.rectangle([6, y + 3, 18, y + 15], fill=PALETTE[i % len(PALETTE)]); td.text((24, y + 2), n, fill=(30, 30, 30), font=font(12))
        for j, (action, (_, _, summary, _)) in enumerate(results.items()):
            s = summary[n]
            r, de = s["share_ratio_median"], s["de_median"]
            bad = (r is not None and not TH_AREA[0] <= r <= TH_AREA[1]) or (de is not None and de > TH_DE)
            txt = f"{r:.2f}x  dE {de:.1f}" if r is not None and de is not None else "missing"
            td.text((130 + j * cw, y + 2), txt, fill=(200, 30, 40) if bad or txt == "missing" else (90, 90, 90), font=font(12))
    hd = header(strip.width, [f"{character}: per-region identity vs {A.load_manifest()['characters'][character]['identity_reference']}",
                              f"Size = region's share of the figure / the reference's share (median over frames; flag outside {TH_AREA[0]}-{TH_AREA[1]}). "
                              f"dE = mean colour distance in Lab (flag > {TH_DE:.0f}). Red = flagged. " + LIMITS], 12)
    stack([hd, strip, tab]).save(path, optimize=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("character")
    s = sub.add_parser("seed"); s.add_argument("character"); s.add_argument("region"); s.add_argument("x", type=int); s.add_argument("y", type=int)
    s = sub.add_parser("compare"); s.add_argument("character"); s.add_argument("actions", nargs="+")
    a = p.parse_args(argv)
    if a.cmd == "init":
        print("wrote", save_seeds(a.character, {k: {"seed": v} for k, v in DEFAULT_SEEDS[a.character].items()}))
    elif a.cmd == "seed":
        seeds = load_seeds(a.character) or {}
        seeds[a.region] = {"seed": [a.x, a.y]}
        print("wrote", save_seeds(a.character, seeds))
    else:
        model = region_model(a.character)
        if not model:
            p.error(f"no seeds: run  python workbench/regions.py init {a.character}")
        results = {}
        for action in a.actions:
            act = A.load_action(a.character, action)
            per, summary, flags = action_regions(act, model)
            results[action] = (act, per, summary, flags)
            print(f"{action}: " + "; ".join(f"{n} {s['share_ratio_median']:.2f}x dE {s['de_median']:.1f}" if s["de_median"] is not None else f"{n} missing"
                                           for n, s in summary.items()))
            for f in flags:
                print("   ", f["code"], f["message"])
        out = A.OUT / a.character / f"regions_{'_'.join(x[:10] for x in a.actions)[:80]}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        compare_image(a.character, results, model, out)
        print("->", out.relative_to(A.ROOT))


if __name__ == "__main__":
    main()
