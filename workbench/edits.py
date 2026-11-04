"""Non-destructive edits stored in an action's annotations/ document (see FORMAT.md, "Edits").

Applied by analysis, preview and export; assets/ is never touched.

    python workbench/edits.py suggest-idle guard idle            # print a proposal
    python workbench/edits.py suggest-idle guard idle --write    # store it in annotations/
    python workbench/edits.py snap guard walk --write            # turn on snap-to-ground
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ANNOTATIONS = ROOT / "annotations"
ALPHA_T = 128


@dataclass
class EditedFrame:
    entry: int            # index into the document's frames list (dropped entries keep their index)
    file: str
    image: np.ndarray     # RGBA after mirror + offset
    duration_ms: float    # duration_ms x hold
    hold: int
    dx: float
    dy: float
    contacts: dict = field(default_factory=dict)   # transformed into the edited frame


def entries(doc: dict | None, files: list[str], default_ms: float) -> list[dict]:
    """The document's frame entries, or one entry per source file when there is no document."""
    if doc and doc.get("frames"):
        return doc["frames"]
    return [{"file": f, "duration_ms": default_ms} for f in files]


def shift(img: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Translate with transparent fill (no wrap-around)."""
    out = np.zeros_like(img)
    h, w = img.shape[:2]
    xs, xd = (0, dx) if dx >= 0 else (-dx, 0)
    ys, yd = (0, dy) if dy >= 0 else (-dy, 0)
    cw, ch = w - abs(dx), h - abs(dy)
    if cw > 0 and ch > 0:
        out[yd:yd + ch, xd:xd + cw] = img[ys:ys + ch, xs:xs + cw]
    return out


def mirror_contacts(contacts: dict, width: int) -> dict:
    return {k: {**c, "x": width - 1 - float(c["x"])} for k, c in contacts.items()}


def move_contacts(contacts: dict, dx: float, dy: float) -> dict:
    return {k: {**c, "x": float(c["x"]) + dx, "y": float(c["y"]) + dy} for k, c in contacts.items()}


def lowest_pixel(img: np.ndarray) -> int | None:
    rows = np.nonzero((img[..., 3] > ALPHA_T).any(axis=1))[0]
    return int(rows.max()) if len(rows) else None


def snap_dy(img: np.ndarray, contacts: dict, ground_y: float) -> float:
    """Vertical shift putting the planted ground foot (or the lowest opaque pixel) on ground_y."""
    feet = [c for n, c in contacts.items() if c.get("state") == "planted" and c.get("surface", "ground") == "ground"
            and n.split("_")[0] in ("foot", "toe", "heel")]
    if feet:
        return ground_y - max(float(c["y"]) for c in feet)
    low = lowest_pixel(img)
    return 0.0 if low is None else ground_y - low


def apply(doc: dict | None, sources: dict[str, np.ndarray], files: list[str], ground_y: float,
          default_ms: float = 1000 / 12) -> list[EditedFrame]:
    """Resolve the document's edits into the frames that are actually played."""
    doc = doc or {}
    mirror = bool(doc.get("mirror"))
    snap_all = bool(doc.get("snap_to_ground"))
    default_ms = doc.get("default_duration_ms", default_ms)
    out = []
    for k, e in enumerate(entries(doc, files, default_ms)):
        if e.get("drop"):
            continue
        img = sources[e["file"]]
        w = img.shape[1]
        contacts = dict(e.get("contacts") or {})
        if mirror:
            img = img[:, ::-1].copy()
            contacts = mirror_contacts(contacts, w)
        ox, oy = (e.get("offset") or [0, 0])
        dy = float(oy)
        if e.get("snap_to_ground", snap_all):
            dy += snap_dy(img, contacts, ground_y)
        dxi, dyi = int(round(ox)), int(round(dy))
        if dxi or dyi:
            img = shift(img, dxi, dyi)
        hold = max(1, int(e.get("hold", 1)))
        out.append(EditedFrame(entry=k, file=e["file"], image=img,
                               duration_ms=float(e.get("duration_ms", default_ms)) * hold, hold=hold,
                               dx=dxi, dy=dyi, contacts=move_contacts(contacts, dxi, dyi)))
    return out


# ---------------------------------------------------------------- suggestions

def suggest_holds(frames: list[np.ndarray], files: list[str], dup: float, base_ms: float = 1000 / 12,
                  calm: float = 2.0, min_ms: float = 250, max_ms: float = 1500) -> list[dict]:
    """Group consecutive near-duplicate poses into one held drawing and slow the timing.

    A run continues while each frame's silhouette is within `dup` of the run's first drawing. The first
    drawing of each run is kept with hold = run length; the rest are marked drop (kept in the document so
    the change is visible). Each held pose lasts run_length x base_ms x calm, clamped to [min_ms, max_ms].
    """
    import analyze  # local import: analyze imports this module
    masks = [analyze._mask(f) for f in frames]
    runs: list[list[int]] = []
    for i in range(len(frames)):
        if runs and analyze.pose_distance(masks[runs[-1][0]], masks[i]) < dup:
            runs[-1].append(i)
        else:
            runs.append([i])
    out = []
    for run in runs:
        total = min(max(len(run) * base_ms * calm, min_ms), max_ms)
        out.append({"file": files[run[0]], "hold": len(run), "duration_ms": round(total / len(run), 1),
                    "note": f"auto-suggest: holds frames {run[0] + 1}-{run[-1] + 1}" if len(run) > 1 else "auto-suggest"})
        for j in run[1:]:
            out.append({"file": files[j], "drop": True, "duration_ms": round(base_ms, 1),
                        "note": f"auto-suggest: near-duplicate of frame {run[0] + 1}, absorbed into its hold"})
    return out


def load_doc(character: str, action: str) -> dict | None:
    p = ANNOTATIONS / character / f"{action}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save_doc(character: str, action: str, doc: dict) -> Path:
    p = ANNOTATIONS / character / f"{action}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return p


def new_doc(character: str, action: str) -> dict:
    import analyze
    man = analyze.load_manifest()
    info = man["characters"][character]["actions"][action]
    files = [f.name for f in sorted((analyze.ASSETS / info["dir"]).glob("*.png"))]
    return {"format": "workbench-action/1", "character": character, "action": action, "source_dir": info["dir"],
            "cell_size": info.get("cell_size", man["conventions"]["cell_size"]),
            "loop_mode": "loop" if info.get("loop") else "once", "default_duration_ms": round(1000 / 12, 1),
            "ground_anchor": {"y": info.get("ground_y", man["conventions"]["ground_y"])}, "facing": "right",
            "frames": [{"file": f, "duration_ms": round(1000 / 12, 1)} for f in files]}


def main(argv=None):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import analyze
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["suggest-idle", "snap"])
    p.add_argument("character")
    p.add_argument("action")
    p.add_argument("--calm", type=float, default=2.0, help="timing multiplier for held poses (default 2)")
    p.add_argument("--write", action="store_true", help="store the result in annotations/")
    a = p.parse_args(argv)
    doc = load_doc(a.character, a.action) or new_doc(a.character, a.action)
    if a.command == "suggest-idle":
        if any(e.get("contacts") for e in doc["frames"]) or any(e.get("drop") or e.get("hold", 1) > 1 for e in doc["frames"]):
            p.error("document already has contacts or holds; edit it in the workbench instead of overwriting")
        act = analyze.load_action(a.character, a.action, use_annotations=False)
        files = [f.name for f in act.files]
        base = float(doc.get("default_duration_ms", 1000 / 12))
        doc["frames"] = suggest_holds(act.frames, files, analyze.TH["duplicate"], base, a.calm)
        doc["edits_note"] = (f"auto-suggested calmer idle: consecutive near-duplicate poses (<{analyze.TH['duplicate']:.0%} "
                             f"silhouette change) held as one drawing, timing x{a.calm}, 250-1500 ms per held pose. A proposal for the owner to judge.")
        kept = [e for e in doc["frames"] if not e.get("drop")]
        print(f"{len(files)} frames -> {len(kept)} held poses, cycle "
              f"{sum(e['duration_ms'] * e['hold'] for e in kept) / 1000:.2f} s (was {len(files) * base / 1000:.2f} s)")
        for e in kept:
            print(f"  {e['file']} hold {e['hold']} x {e['duration_ms']} ms  ({e['note']})")
    else:
        doc["snap_to_ground"] = True
        print("snap_to_ground on: each frame's planted ground foot (or lowest pixel) moves to ground y "
              f"{doc['ground_anchor']['y']}")
    if a.write:
        print("wrote", save_doc(a.character, a.action, doc).relative_to(ROOT))


if __name__ == "__main__":
    main()
