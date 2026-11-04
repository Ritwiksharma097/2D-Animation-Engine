"""Frame analysis for sprite actions.

Library + CLI. Every metric is a heuristic; results are "suspect" flags, never passes.

    python workbench/analyze.py guard walk
    python workbench/analyze.py ren walk_keypose --travel 41.9
    python workbench/analyze.py --all

See FORMAT.md for the report and annotation formats.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ANNOTATIONS = ROOT / "annotations"
OUT = ROOT / "out"

ALPHA_T = 128  # alpha above this counts as opaque figure

# Thresholds are chosen up front from first principles, not tuned on the data.
TH = {
    "diff_pixel": 0.15,        # per-pixel colour change (0..1) that counts as "changed"
    "duplicate": 0.03,         # silhouette change (1 - IoU) below this = near-duplicate pose
    "detail_boil": 0.25,       # redrawn fraction of shared silhouette that is suspicious when the pose barely moves
    "uneven_hi": 1.8,          # step change above this x median = jump
    "uneven_lo": 0.5,          # step change below this x median = stall
    "uneven_cv": 0.35,         # coefficient of variation of step changes
    "height_rel": 0.04,        # frame height off action median by more than 4%
    "ref_height_rel": 0.06,    # frame height off identity reference by more than 6%
    "ref_proportion_rel": 0.12,  # head-width/height or bulk off reference by >12%
    "palette_tv": 0.15,        # palette histogram total-variation distance vs reference
    "palette_de": 6.0,         # extra mean colour error (Lab) vs the reference's own error
    "baseline_px": 3,          # lowest pixel off ground_y
    "foot_band": 0.12,         # foot band = bottom 12% of figure height
    "plant_tol": 0.012,        # cluster counts as planted if its sole is this close to baseline (x height)
    "slide_step_px": 4.0,      # planted-foot slide per step (cell px) worth flagging ...
    "slide_step_rel": 0.15,    # ... or more than 15% of the travel per frame
    "passing_ratio": 0.45,     # a clear passing pose has stride below this x max stride
}

LIMITS = {
    "change": "Pose change is silhouette change (1 - IoU of opaque masks at 1/4 resolution, in cell position). It cannot tell a meaningful pose change from an equal-sized change in an unimportant area (a swinging satchel), and it ignores changes inside the outline (a face, a hand in front of the body). Detail change measures those, but also counts harmless shading differences.",
    "duplicates": "Near-duplicate poses use a fixed silhouette threshold (3%); two drawings that differ only inside the outline (eyes, mouth) count as duplicates of pose even if detail differs.",
    "order": "Out-of-order detection looks for frames closer to a non-neighbour than to both neighbours. In a side-view walk the frame half a cycle later is expected to look similar (legs swapped), so those partners are excluded and reported separately.",
    "geometry": "Height, width and baseline come from the opaque-pixel bounding box; raised arms, a swinging bag or a cropped frame change them without the character changing.",
    "identity": "Identity drift is judged only by size, two crude proportions and colour palette. It cannot see a changed face, hood shape or costume detail if colours and size stay similar. A reference in a different pose or scale (guard concept art) makes size comparisons meaningless, so they are skipped there.",
    "feet": "Feet are estimated as opaque clusters in the bottom 12% of the figure. Overlapping feet merge into one cluster, long robes or shadows are mistaken for feet, and the contact point is the middle of the sole, so a normal heel-to-toe roll reads as a few pixels of slide.",
    "slide": "Without annotations, the planted foot in each step is assumed to be whichever pairing of ground contacts would slide least. The reported slide is therefore a lower bound: the real slide may be larger if the wrong foot was matched. With annotations, contacts are matched by name and every shared planted contact must stay put; the result is only as good as the clicked points.",
    "stride": "Stride is the horizontal spread of foot clusters; a lifted foot above the foot band does not count, so passing poses read as stride 0 by construction.",
}


# ---------------------------------------------------------------- loading

@dataclass
class Action:
    character: str
    action: str
    files: list[Path]
    frames: list[np.ndarray]           # HxWx4 uint8 RGBA
    durations_ms: list[float]
    loop_mode: str = "loop"
    ground_y: float = 535
    facing: str = "right"
    travel: float | list | None = None  # cell px per frame: constant, or a per-step list
    travel_source: str = "none"
    travel_mode: str | None = None      # constant | per_frame | from_contacts (FORMAT.md)
    game_scale: float | None = None
    is_walk: bool = False
    status: str = ""
    feedback: str = ""
    reference: np.ndarray | None = None
    reference_path: str | None = None
    annotations: dict | None = None
    annotation_path: Path | None = None
    meta: dict = field(default_factory=dict)


def load_manifest() -> dict:
    return json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))


def load_rgba(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.array(im.convert("RGBA"))


def parse_travel(old_timing: str | None) -> float | None:
    """Pull '= ~41.9 cell px' out of the manifest's old_timing note."""
    if not old_timing:
        return None
    m = re.search(r"~\s*([\d.]+)\s*cell px", old_timing)
    return float(m.group(1)) if m else None


def load_action(character: str, action: str, travel: float | None = None,
                use_annotations: bool = True) -> Action:
    man = load_manifest()
    ch = man["characters"][character]
    info = ch["actions"][action]
    src = ASSETS / info["dir"]
    ann_path = ANNOTATIONS / character / f"{action}.json"
    ann = None
    if use_annotations and ann_path.exists():
        ann = json.loads(ann_path.read_text(encoding="utf-8"))
    default_ms = (ann or {}).get("default_duration_ms", 1000 / 12)
    if ann and ann.get("frames"):
        files = [src / f["file"] for f in ann["frames"]]
        durations = [float(f.get("duration_ms", default_ms)) for f in ann["frames"]]
    else:
        files = sorted(src.glob("*.png"))
        durations = [default_ms] * len(files)
    ref_rel = ch.get("identity_reference")
    ref = load_rgba(ASSETS / ref_rel) if ref_rel and (ASSETS / ref_rel).exists() else None
    loop_mode = (ann or {}).get("loop_mode") or ("loop" if info.get("loop") else "once")
    t_src, t_mode = "none", None
    at = (ann or {}).get("travel") or {}
    if travel is not None:
        t_src, t_mode = "command line", "constant"
    elif at.get("mode") == "constant":
        travel, t_src, t_mode = float(at["px_per_frame"]), "annotation file", "constant"
    elif at.get("mode") == "per_frame":
        travel, t_src, t_mode = [float(v) for v in at["px_per_frame"]], "annotation file (per frame)", "per_frame"
    elif at.get("mode") == "from_contacts":
        travel, t_src, t_mode = None, "derived from planted contacts (annotation file)", "from_contacts"
    elif parse_travel(info.get("old_timing")) is not None:
        travel, t_src, t_mode = parse_travel(info.get("old_timing")), "manifest old_timing", "constant"
    return Action(
        character=character, action=action, files=files,
        frames=[load_rgba(f) for f in files], durations_ms=durations,
        loop_mode=loop_mode,
        ground_y=float((ann or {}).get("ground_anchor", {}).get("y", man["conventions"].get("ground_y", 535))),
        facing=(ann or {}).get("facing", "right"),
        travel=travel, travel_source=t_src, travel_mode=t_mode,
        game_scale=ch.get("game_scale_in_old_demos"),
        is_walk="walk" in action, status=info.get("status", ""), feedback=info.get("feedback", ""),
        reference=ref, reference_path=ref_rel, annotations=ann,
        annotation_path=ann_path if ann else None,
    )


# ---------------------------------------------------------------- frame change

SMALL = (160, 144)  # analysis resolution for change metrics (cell / 4)


def _mask(frame: np.ndarray) -> np.ndarray:
    a = cv2.resize(frame[..., 3].astype(np.float32) / 255.0, SMALL, interpolation=cv2.INTER_AREA)
    return a > 0.5


def _rgb(frame: np.ndarray) -> np.ndarray:
    return cv2.resize(frame[..., :3].astype(np.float32) / 255.0, SMALL, interpolation=cv2.INTER_AREA)


def pose_distance(ma: np.ndarray, mb: np.ndarray) -> float:
    """Silhouette change: 1 - IoU of the opaque masks (0 = same outline)."""
    union = (ma | mb).sum()
    return float(1 - (ma & mb).sum() / union) if union else 0.0


def detail_distance(ma, mb, ca, cb) -> float:
    """Fraction of the shared silhouette whose colour changed (redrawn detail / 'boil')."""
    inter = ma & mb
    if not inter.any():
        return 1.0
    changed = np.abs(ca - cb).max(axis=2) > TH["diff_pixel"]
    return float((changed & inter).sum() / inter.sum())


def frame_distance(a: np.ndarray, b: np.ndarray) -> float:
    return pose_distance(_mask(a), _mask(b))


def distance_matrices(frames: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    n = len(frames)
    ms = [_mask(f) for f in frames]
    cs = [_rgb(f) for f in frames]
    pose, detail = np.zeros((n, n)), np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            pose[i, j] = pose[j, i] = pose_distance(ms[i], ms[j])
            detail[i, j] = detail[j, i] = detail_distance(ms[i], ms[j], cs[i], cs[j])
    return pose, detail


def distance_matrix(frames: list[np.ndarray]) -> np.ndarray:
    return distance_matrices(frames)[0]


def steps(n: int, loop: bool) -> list[tuple[int, int]]:
    s = [(i, i + 1) for i in range(n - 1)]
    if loop and n > 2:
        s.append((n - 1, 0))
    return s


def cyc(i: int, j: int, n: int, loop: bool) -> int:
    d = abs(i - j)
    return min(d, n - d) if loop else d


def change_analysis(d: np.ndarray, loop: bool, is_walk: bool) -> dict:
    n = len(d)
    st = steps(n, loop)
    vals = np.array([d[i, j] for i, j in st]) if st else np.array([])
    med = float(np.median(vals)) if len(vals) else 0.0
    cv = float(vals.std() / vals.mean()) if len(vals) and vals.mean() > 0 else 0.0
    dups = [(i, j, float(d[i, j])) for i in range(n) for j in range(i + 1, n) if d[i, j] < TH["duplicate"]]
    # distinct drawings: greedy clustering on the duplicate threshold
    labels = [-1] * n
    k = 0
    for i in range(n):
        if labels[i] < 0:
            for j in range(i, n):
                if labels[j] < 0 and d[i, j] < TH["duplicate"]:
                    labels[j] = k
            k += 1
    out_of_order, half_cycle = [], []
    if n >= 4:
        for i in range(n):
            nb = [j for j in range(n) if j != i and cyc(i, j, n, loop) == 1]
            if not nb:
                continue
            nb_d = min(d[i, j] for j in nb)
            for j in range(n):
                c = cyc(i, j, n, loop)
                if c <= 1:
                    continue
                if is_walk and loop and abs(c - n / 2) <= 1:
                    if d[i, j] < nb_d:
                        half_cycle.append((i, j, float(d[i, j])))
                    continue
                if d[i, j] < nb_d:
                    out_of_order.append((i, j, float(d[i, j]), float(nb_d)))
    return {
        "steps": [[i, j, float(d[i, j])] for i, j in st],
        "step_median": med, "step_cv": cv,
        "near_duplicates": dups, "distinct_drawings": k, "cluster_labels": labels,
        "out_of_order": out_of_order, "half_cycle_lookalikes": half_cycle,
    }


# ---------------------------------------------------------------- geometry & palette

def figure_geometry(frame: np.ndarray) -> dict:
    m = frame[..., 3] > ALPHA_T
    ys, xs = np.nonzero(m)
    if len(ys) == 0:
        return {"empty": True}
    top, bottom, left, right = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    h, w = bottom - top + 1, right - left + 1
    head_rows = m[top: top + max(1, int(0.25 * h))]
    hx = np.nonzero(head_rows.any(axis=0))[0]
    return {
        "bbox": [left, top, right, bottom], "height": h, "width": w, "baseline": bottom,
        "area": int(m.sum()),
        "head_width_ratio": float((hx.max() - hx.min() + 1) / h) if len(hx) else 0.0,
        "bulk": float(m.sum() / (h * h)),
        "touches_edge": bool(left == 0 or top == 0 or right == m.shape[1] - 1 or bottom == m.shape[0] - 1),
    }


def _lab_pixels(frame: np.ndarray, max_px=40000, seed=0) -> np.ndarray:
    m = frame[..., 3] > ALPHA_T
    rgb = frame[..., :3][m]
    if len(rgb) > max_px:
        rgb = rgb[np.random.default_rng(seed).choice(len(rgb), max_px, replace=False)]
    lab = cv2.cvtColor(rgb.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).reshape(-1, 3)
    lab = lab.astype(np.float32)
    lab[:, 0] *= 100 / 255.0
    lab[:, 1:] -= 128
    return lab


def palette(frame: np.ndarray, k=8) -> np.ndarray:
    lab = _lab_pixels(frame)
    cv2.setRNGSeed(1)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.2)
    _, _, centres = cv2.kmeans(lab, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    return centres


def palette_stats(frame: np.ndarray, centres: np.ndarray) -> dict:
    lab = _lab_pixels(frame)
    dist = np.linalg.norm(lab[:, None, :] - centres[None, :, :], axis=2)
    nearest = dist.argmin(axis=1)
    hist = np.bincount(nearest, minlength=len(centres)) / max(len(nearest), 1)
    return {"hist": hist, "mean_de": float(dist.min(axis=1).mean())}


def lab_to_hex(c: np.ndarray) -> str:
    lab = np.array([[[c[0] * 255 / 100, c[1] + 128, c[2] + 128]]], dtype=np.float32).clip(0, 255).astype(np.uint8)
    r, g, b = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)[0, 0]
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------------------------------------------------------------- feet

def foot_clusters(frame: np.ndarray) -> dict:
    """Opaque clusters in the bottom band of the figure, with contact points."""
    g = figure_geometry(frame)
    if g.get("empty"):
        return {"clusters": [], "stride": 0.0, "baseline": None}
    m = (frame[..., 3] > ALPHA_T).astype(np.uint8)
    base, h = g["baseline"], g["height"]
    band_h = max(3, int(round(TH["foot_band"] * h)))
    tol = max(2, int(round(TH["plant_tol"] * h)))
    y0 = base - band_h + 1
    band = m[y0: base + 1]
    n, lab, stats, _ = cv2.connectedComponentsWithStats(band, connectivity=8)
    clusters = []
    for c in range(1, n):
        if stats[c, cv2.CC_STAT_AREA] < max(20, 0.03 * band.sum()):
            continue
        ys, xs = np.nonzero(lab == c)
        low = int(ys.max()) + y0
        sole = xs[ys + y0 >= low - tol]
        clusters.append({
            "x": float(sole.mean()), "y": float(low),
            "x0": int(xs.min()), "x1": int(xs.max()),
            "centroid_x": float(xs.mean()),
            "planted": bool(low >= base - tol),
            "area": int(len(xs)),
        })
    clusters.sort(key=lambda c: c["x"])
    stride = clusters[-1]["centroid_x"] - clusters[0]["centroid_x"] if len(clusters) >= 2 else 0.0
    return {"clusters": clusters, "stride": float(stride), "baseline": base, "band_top": y0, "tol": tol}


def contacts_from_annotations(ann: dict, n: int) -> list[list[dict]] | None:
    """Planted ground-foot contacts per frame from an annotation file, or None if none annotated."""
    frames = ann.get("frames") or []
    if len(frames) != n or not any(f.get("contacts") for f in frames):
        return None
    out = []
    for f in frames:
        cs = []
        for name, c in (f.get("contacts") or {}).items():
            cs.append({"name": name, "x": float(c["x"]), "y": float(c["y"]),
                       "planted": c.get("state") == "planted", "surface": c.get("surface", "ground")})
        out.append(cs)
    return out


def is_foot(name: str) -> bool:
    return name.split("_")[0] in ("foot", "toe", "heel")


def step_pairs(ca: list[dict], cb: list[dict], sign: float, named: bool) -> list[float]:
    """Candidate travel values d for one step: how far the character must advance for a contact to stay put."""
    pa = [c for c in ca if c["planted"]]
    pb = [c for c in cb if c["planted"]]
    ds = []
    for a in pa:
        for b in pb:
            if named and (a["name"] != b["name"] or a.get("surface") != b.get("surface")):
                continue
            ds.append(sign * (a["x"] - b["x"]))
    return ds


def slide_for_travel(step_ds: list[list[float]], travel: list[float] | float, named: bool = False) -> list[float | None]:
    """Slide per step. Heuristic (unnamed) contacts: the least-sliding pairing (a lower bound).
    Named (annotated) contacts: every shared planted contact must stay put, so the worst one counts."""
    tr = travel if isinstance(travel, list) else [travel] * len(step_ds)
    agg = max if named else min
    return [agg(abs(d - t) for d in ds) if ds else None for ds, t in zip(step_ds, tr)]


def best_constant_travel(step_ds: list[list[float]], vmax: float, vmin: float = 0.0) -> float:
    """Constant travel per frame in [vmin, vmax] minimising total planted-foot slide (L1, robust)."""
    if not any(step_ds) or vmax <= vmin:
        return float(vmin)
    grid = np.arange(vmin, vmax, 0.25)
    cost = [sum(s for s in slide_for_travel(step_ds, float(v)) if s is not None) for v in grid]
    return float(grid[int(np.argmin(cost))])


def chosen_ds(step_ds: list[list[float]], v: float) -> list[float | None]:
    return [min(ds, key=lambda d: abs(d - v)) if ds else None for ds in step_ds]


def stride_segments(vals: list[float], loop: bool) -> tuple[list[list[int]], list[list[int]]]:
    """Split frames into runs below / above the stride midpoint. Each low run is one passing phase (one step)."""
    n = len(vals)
    if n == 0 or max(vals) == min(vals):
        return [], []
    mid = 0.5 * (max(vals) + min(vals))
    low = [v < mid for v in vals]
    start = 0
    if loop and all(low[i] == low[0] for i in range(n)) is False:
        # rotate so we start at a boundary and wrap-around runs stay whole
        start = next(i for i in range(n) if low[i] != low[i - 1])
    order = [(start + k) % n for k in range(n)] if loop else list(range(n))
    lows, highs, cur = [], [], [order[0]]
    for i in order[1:]:
        if low[i] == low[cur[-1]]:
            cur.append(i)
        else:
            (lows if low[cur[-1]] else highs).append(cur)
            cur = [i]
    (lows if low[cur[-1]] else highs).append(cur)
    return lows, highs


def walk_analysis(act: Action, foot: list[dict]) -> dict:
    n = len(act.frames)
    loop = act.loop_mode == "loop"
    sign = 1.0 if act.facing == "right" else -1.0
    ann_contacts = contacts_from_annotations(act.annotations, n) if act.annotations else None
    if ann_contacts:
        contacts = [[c for c in cs if is_foot(c["name"])] for cs in ann_contacts]
        source = "annotations"
    else:
        contacts = [[{**c, "name": f"cluster{k}", "surface": "ground"} for k, c in enumerate(f["clusters"])] for f in foot]
        source = "heuristic"
    st = steps(n, loop)
    step_ds = [step_pairs(contacts[i], contacts[j], sign, named=source == "annotations") for i, j in st]
    strides = [f["stride"] for f in foot]
    smax = max(strides) if strides else 0.0
    lows, highs = stride_segments(strides, loop)
    kinds = ["between"] * n
    for run in lows:
        kinds[min(run, key=lambda i: strides[i])] = "passing"
    for run in highs:
        kinds[max(run, key=lambda i: strides[i])] = "contact"
    heights = [figure_geometry(fr)["height"] for fr in act.frames]
    vmax = 0.3 * float(np.median(heights)) if heights else 0
    # A cycle has two steps; each step the stance foot travels back about one contact stride.
    contact_strides = [strides[i] for i, k in enumerate(kinds) if k == "contact"] or [smax]
    v_stride = 2 * float(np.median(contact_strides)) / max(len(st), 1)
    named = source == "annotations"
    unconstrained = best_constant_travel(step_ds, vmax)
    best = best_constant_travel(step_ds, 1.6 * v_stride, 0.4 * v_stride)
    if named:
        # exact: the advance that keeps each step's shared planted contacts fixed (mean if several)
        derived = [float(np.mean(ds)) if ds else None for ds in step_ds]
        known = [v for v in derived if v is not None]
        fill = float(np.mean(known)) if known else best
        per_frame = derived
        if known:
            best = best_constant_travel(step_ds, max(vmax, 1.2 * max(known)), 0.0)
    else:
        per_frame = chosen_ds(step_ds, best)
    if act.travel_mode == "from_contacts" and named:
        used_travel = [v if v is not None else fill for v in per_frame]
    elif act.travel_mode == "per_frame" and isinstance(act.travel, list):
        used_travel = (act.travel + [act.travel[-1]] * len(st))[:len(st)]
    elif act.travel is not None:
        used_travel = act.travel
    else:
        used_travel = best
    slides = slide_for_travel(step_ds, used_travel, named)
    best_slides = slide_for_travel(step_ds, best, named)
    used_mean = float(np.mean(used_travel)) if isinstance(used_travel, list) else float(used_travel)
    valid = [s for s in slides if s is not None]
    scale = act.game_scale
    return {
        "contact_source": source,
        "stride_px": strides,
        "pose_kind": kinds,
        "contact_frames": [i for i, k in enumerate(kinds) if k == "contact"],
        "passing_frames": [i for i, k in enumerate(kinds) if k == "passing"],
        "steps_per_loop": len(lows),
        "passing_runs": lows,
        "min_max_stride_ratio": float(min(strides) / smax) if smax else None,
        "contacts": [[{k: c[k] for k in ("name", "x", "y", "planted")} for c in cs] for cs in contacts],
        "steps": [[i, j] for i, j in st],
        "step_candidate_travel": step_ds,
        "travel_used_px": used_mean,
        "travel_used_per_step_px": used_travel if isinstance(used_travel, list) else None,
        "travel_used_source": act.travel_source if act.travel_mode else "recommended (no travel given)",
        "steps_without_shared_contact": [list(s) for s, ds in zip(st, step_ds) if not ds],
        "slide_per_step_px": slides,
        "slide_total_px": float(sum(valid)),
        "slide_max_px": float(max(valid)) if valid else None,
        "slide_total_game_px": float(sum(valid) * scale) if scale else None,
        "stride_based_travel_px": v_stride,
        "unconstrained_best_travel_px": unconstrained,
        "slide_curve": [[float(v), float(sum(x for x in slide_for_travel(step_ds, float(v), named) if x is not None))]
                        for v in np.arange(0, max(vmax, 1.7 * v_stride), 1.0)],
        "recommended_travel_px": best,
        "recommended_travel_game_px": best * scale if scale else None,
        "slide_at_recommended_px": best_slides,
        "slide_total_at_recommended_px": float(sum(s for s in best_slides if s is not None)),
        "recommended_per_frame_travel_px": per_frame,
        "travel_per_loop_px": float(used_mean * len(st)),
    }


# ---------------------------------------------------------------- whole report

def analyze(act: Action) -> dict:
    n = len(act.frames)
    loop = act.loop_mode == "loop"
    d, detail = distance_matrices(act.frames)
    ch = change_analysis(d, loop, act.is_walk)
    st = steps(n, loop)
    ch["detail_steps"] = [[i, j, float(detail[i, j])] for i, j in st]
    geo = [figure_geometry(f) for f in act.frames]
    flags: list[dict] = []

    def flag(code, frames, msg):
        flags.append({"level": "suspect", "code": code, "frames": sorted({int(f) + 1 for f in frames}), "message": msg})

    def seam(j):
        return " (loop seam)" if j == 0 and loop else ""

    # --- change
    if n > 1:
        med = ch["step_median"]
        for i, j, v in ch["steps"]:
            if med > 0 and v > TH["uneven_hi"] * med:
                flag("uneven_jump", [i, j], f"Frame {i+1}->{j+1}{seam(j)}: pose changes {v/med:.1f}x the median step (a jump).")
            elif med > 0 and v < TH["uneven_lo"] * med:
                flag("uneven_stall", [i, j], f"Frame {i+1}->{j+1}{seam(j)}: pose changes only {v/med:.2f}x the median step (a stall).")
        if ch["step_cv"] > TH["uneven_cv"]:
            flag("uneven_overall", [], f"Step-to-step pose change is uneven (coefficient of variation {ch['step_cv']:.2f}).")
        if ch["near_duplicates"]:
            pairs = ", ".join(f"{i+1}~{j+1}" for i, j, _ in ch["near_duplicates"])
            flag("near_duplicate", [k for i, j, _ in ch["near_duplicates"] for k in (i, j)],
                 f"Near-duplicate poses (silhouette differs <{TH['duplicate']:.0%}): {pairs}.")
        if ch["distinct_drawings"] < n:
            flag("few_distinct", [], f"Only about {ch['distinct_drawings']} distinct poses among {n} frames.")
        if ch["out_of_order"]:
            pairs = ", ".join(f"{i+1}->{j+1}" for i, j, _, _ in ch["out_of_order"])
            flag("out_of_order", [i for i, *_ in ch["out_of_order"]],
                 f"Frames closer to a non-neighbour than to either neighbour (repeated pose or wrong order): {pairs}.")
        boil = [(i, j) for (i, j, v), (_, _, dv) in zip(ch["steps"], ch["detail_steps"])
                if v < 2 * TH["duplicate"] and dv > TH["detail_boil"]]
        if boil:
            flag("redrawn_detail", [k for p in boil for k in p],
                 "Pose barely moves but much of the inside is redrawn (detail flicker/boil): " + ", ".join(f"{i+1}->{j+1}" for i, j in boil) + ".")

    # --- geometry
    heights = np.array([g["height"] for g in geo], float)
    hmed = float(np.median(heights))
    bad = [i for i, g in enumerate(geo) if abs(g["height"] - hmed) > TH["height_rel"] * hmed]
    if bad:
        flag("height_drift", bad, f"Height differs from the action median ({hmed:.0f}px) by >{TH['height_rel']:.0%}: " + ", ".join(f"{i+1}:{geo[i]['height']}" for i in bad) + ".")
    bases = [g["baseline"] for g in geo]
    bad = [i for i, b in enumerate(bases) if abs(b - act.ground_y) > TH["baseline_px"]]
    if bad:
        flag("baseline_off", bad, f"Lowest pixel is off the ground line y={act.ground_y:.0f} by >{TH['baseline_px']}px (range {min(bases)}-{max(bases)}); the figure floats or sinks.")
    if max(bases) - min(bases) > TH["baseline_px"]:
        flag("baseline_jitter", [int(np.argmin(bases)), int(np.argmax(bases))], f"Lowest pixel moves {max(bases) - min(bases)}px between frames; feet bob against the ground.")
    bad = [i for i, g in enumerate(geo) if g["touches_edge"]]
    if bad:
        flag("cropped", bad, "Figure touches the cell edge (possibly cropped).")

    # --- identity vs reference
    identity = {"reference": act.reference_path}
    if act.reference is not None:
        rg = figure_geometry(act.reference)
        same_cell = act.reference.shape[:2] == act.frames[0].shape[:2]
        centres = palette(act.reference)
        ref_pal = palette_stats(act.reference, centres)
        pals = [palette_stats(f, centres) for f in act.frames]
        tv = [float(0.5 * np.abs(p["hist"] - ref_pal["hist"]).sum()) for p in pals]
        de = [p["mean_de"] - ref_pal["mean_de"] for p in pals]
        identity.update({
            "same_cell_size": same_cell,
            "reference_geometry": rg,
            "reference_palette": [lab_to_hex(c) for c in centres],
            "reference_palette_hist": ref_pal["hist"].tolist(),
            "palette_hist": [p["hist"].tolist() for p in pals],
            "palette_tv": tv, "palette_extra_de": de,
            "height_ratio": [g["height"] / rg["height"] for g in geo] if same_cell else None,
            "head_width_ratio_rel": [g["head_width_ratio"] / rg["head_width_ratio"] for g in geo],
            "bulk_rel": [g["bulk"] / rg["bulk"] for g in geo],
        })
        bad_tv = [i for i, v in enumerate(tv) if v > TH["palette_tv"]]
        bad_de = [i for i, v in enumerate(de) if v > TH["palette_de"]]
        if bad_tv:
            flag("palette_drift", bad_tv, f"Colour proportions differ from the identity reference (total variation {min(tv):.2f}-{max(tv):.2f}, limit {TH['palette_tv']}).")
        if bad_de:
            flag("palette_new_colours", bad_de, f"Colours not in the reference palette (extra mean error up to {max(de):.1f} Lab units).")
        if same_cell:
            hr = identity["height_ratio"]
            bad = [i for i, v in enumerate(hr) if abs(v - 1) > TH["ref_height_rel"]]
            if bad:
                flag("scale_drift", bad, f"Figure height is {min(hr):.2f}-{max(hr):.2f}x the identity reference.")
        for key, code, label in (("head_width_ratio_rel", "proportion_head", "head-region width / height"),
                                 ("bulk_rel", "proportion_bulk", "area / height^2 (thinness)")):
            mean_v = float(np.mean(identity[key]))
            if abs(mean_v - 1) > TH["ref_proportion_rel"]:
                flag(code, [], f"Mean {label} is {mean_v:.2f}x the identity reference{'' if same_cell else ' (reference is a different drawing; weak evidence)'}.")

    # --- walk
    walk = None
    foot = [foot_clusters(f) for f in act.frames]
    if act.is_walk and n > 1:
        walk = walk_analysis(act, foot)
        ratio = walk["min_max_stride_ratio"]
        if ratio is None or ratio > TH["passing_ratio"]:
            flag("no_passing_pose", [], f"Narrowest stride is {ratio or 0:.0%} of the widest (limit {TH['passing_ratio']:.0%}): no clear passing pose where the feet come together.")
        if loop and walk["steps_per_loop"] != 2:
            flag("step_count", walk["passing_frames"], f"Stride narrows {walk['steps_per_loop']} times per loop; a walk cycle has 2 steps. Frames may repeat a step or break the rhythm.")
        tr = walk["travel_used_px"]
        lim = max(TH["slide_step_px"], TH["slide_step_rel"] * tr)
        bad = [(i, j, s) for (i, j), s in zip(walk["steps"], walk["slide_per_step_px"]) if s is not None and s > lim]
        if bad:
            flag("foot_slide", [k for i, j, _ in bad for k in (i, j)],
                 f"At travel {tr:.1f} px/frame{' (mean of per-step values)' if walk['travel_used_per_step_px'] else ''} the planted foot slides {'at least ' if walk['contact_source'] == 'heuristic' else ''}more than {lim:.1f}px in {len(bad)}/{len(walk['steps'])} steps: "
                 + ", ".join(f"{i+1}->{j+1}:{s:.0f}" for i, j, s in bad) + ".")
        rec = walk["recommended_travel_px"]
        if act.travel_mode == "constant" and rec and abs(tr - rec) > TH["slide_step_rel"] * rec:
            flag("travel_mismatch", [], f"Travel {tr:.1f} px/frame differs from the slide-minimising {rec:.1f} px/frame.")
        if walk["steps_without_shared_contact"]:
            flag("no_shared_contact", [k for s in walk["steps_without_shared_contact"] for k in s],
                 "Steps with no contact planted in both frames (nothing can stay put; travel there is a guess): "
                 + ", ".join(f"{i+1}->{j+1}" for i, j in walk["steps_without_shared_contact"]) + ".")
        if walk["unconstrained_best_travel_px"] < 0.25 * walk["stride_based_travel_px"]:
            flag("stance_not_moving", [], f"Planted feet barely move backward across the cycle (least slide at {walk['unconstrained_best_travel_px']:.1f} px/frame, "
                 f"while the stride implies ~{walk['stride_based_travel_px']:.0f}): the drawings shuffle in place, so any travel slides.")
        rec_s = walk["slide_at_recommended_px"]
        lim_r = max(TH["slide_step_px"], TH["slide_step_rel"] * rec)
        bad = [k for k, s in enumerate(rec_s) if s is not None and s > lim_r]
        if bad:
            flag("slide_unavoidable", [k2 for k in bad for k2 in walk["steps"][k]],
                 f"Even at the best constant travel ({rec:.1f} px/frame) {len(bad)} step(s) slide more than {lim_r:.1f}px: stance-foot motion is uneven, so constant speed cannot hide it.")

    report = {
        "character": act.character, "action": act.action,
        "source": [str(f.relative_to(ROOT)).replace("\\", "/") for f in act.files],
        "frame_count": n, "status_in_manifest": act.status, "owner_feedback": act.feedback,
        "settings": {"loop_mode": act.loop_mode, "ground_y": act.ground_y, "facing": act.facing,
                     "travel_px_per_frame": act.travel, "travel_source": act.travel_source,
                     "game_scale": act.game_scale, "durations_ms": act.durations_ms,
                     "annotations": str(act.annotation_path.relative_to(ROOT)).replace("\\", "/") if act.annotation_path else None,
                     "thresholds": TH},
        "metrics": {"pose_distance_matrix": d.round(4).tolist(), "detail_distance_matrix": detail.round(4).tolist(),
                    "change": ch, "geometry": geo, "feet": foot, "identity": identity, "walk": walk},
        "flags": flags, "limits": LIMITS,
    }
    report["summary"] = summarize(report)
    return report


def summarize(r: dict) -> str:
    n, ch, walk = r["frame_count"], r["metrics"]["change"], r["metrics"]["walk"]
    codes = {}
    for f in r["flags"]:
        codes.setdefault(f["code"], []).append(f)
    codes = {k: v for k, v in codes.items()}
    lines = [f"{r['character']}/{r['action']}: {n} frames, about {ch['distinct_drawings']} distinct poses, "
             f"median pose change per frame {ch['step_median']:.1%} of the silhouette (variation {ch['step_cv']:.2f})."]
    if walk:
        tr = walk["travel_used_px"]
        lines.append(f"Walk (contacts from {walk['contact_source']}): {len(walk['contact_frames'])} contact and "
                     f"{len(walk['passing_frames'])} passing pose(s), {walk['steps_per_loop']} step(s) per loop, narrowest/widest stride {walk['min_max_stride_ratio'] or 0:.0%}. "
                     f"At {tr:.1f} px/frame ({walk['travel_used_source']}) the planted foot slides {'at least ' if walk['contact_source'] == 'heuristic' else ''}"
                     f"{walk['slide_total_px']:.0f} px per loop (worst step {walk['slide_max_px'] or 0:.1f} px). "
                     f"Slide-minimising constant travel is {walk['recommended_travel_px']:.1f} px/frame, leaving "
                     f"{walk['slide_total_at_recommended_px']:.0f} px of slide per loop.")
    if codes:
        lines.append("Suspect: " + ", ".join(codes) + ".")
    else:
        lines.append("No suspect flags. That is not a pass: see limits.")
    return " ".join(lines)


def output_dir(character: str, action: str) -> Path:
    p = OUT / character / action
    p.mkdir(parents=True, exist_ok=True)
    return p


def run(character: str, action: str, travel: float | None = None, images: bool = True,
        use_annotations: bool = True) -> dict:
    act = load_action(character, action, travel, use_annotations)
    rep = analyze(act)
    od = output_dir(character, action)
    (od / "report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    if images:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import diagnostics
        rep["images"] = diagnostics.write_all(act, rep, od)
        (od / "report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return rep


DEFAULT_SET = [("guard", "walk"), ("guard", "idle"), ("ren", "walk_keypose"),
               ("ren", "rejected_walk_fourteen"), ("ren", "rejected_walk_flatboy")]


def main(argv=None):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("character", nargs="?")
    p.add_argument("action", nargs="?")
    p.add_argument("--travel", type=float, help="travel per frame in cell px (overrides manifest)")
    p.add_argument("--all", action="store_true", help="analyse the standard real-data set")
    p.add_argument("--no-images", action="store_true")
    p.add_argument("--no-annotations", action="store_true", help="ignore annotations/ and use heuristics")
    a = p.parse_args(argv)
    todo = DEFAULT_SET if a.all else [(a.character, a.action)]
    if not a.all and not (a.character and a.action):
        p.error("give CHARACTER ACTION or --all")
    for c, ac in todo:
        rep = run(c, ac, a.travel, not a.no_images, not a.no_annotations)
        print(rep["summary"])
        print(f"  -> {(OUT / c / ac / 'report.json').relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()
