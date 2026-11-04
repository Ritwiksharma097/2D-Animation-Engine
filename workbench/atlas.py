"""Merge each character's exports into a few atlas pages, so a page loads one JSON and one or two images per character.

    python workbench/atlas.py            # after export.py: writes out/export/<character>/_atlas.json + _atlas_<n>.png

Clips are grouped (GROUPS): the "core" group (what every screen needs) goes on its own page(s) and the rest after it, so
a level that never climbs or jumps doesn't load those drawings. Each clip's sheet is placed whole (it is already packed)
and its JSON is embedded with the sheet's offset, so runtime/anim.js `loadAtlasClips` can shift the frame rects. Pages
are at most 4096 px a side (a texture size every current browser and GPU accepts). Per-clip files stay as they are.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze as A  # noqa: E402

EXPORT = A.OUT / "export"
MAX = 4096
GROUPS = {   # first group = core (every screen of the sandbox needs it); clips not listed go into the last group
    "ren": [["idle", "walk_keypose", "interact", "caught_game_over", "look_around"], ["climb_up", "climb_down", "jump", "happy", "hurt_stumble"]],
    "guard": [["idle", "walk", "angry", "eating"], ["happy", "love", "ladder_up"]],
}


def shelf(sizes):
    """Shelf-pack (w, h) boxes into pages of at most MAX x MAX. Returns [(page, x, y)] in input order."""
    out, page, x, y, row = [None] * len(sizes), 0, 0, 0, 0
    for i in sorted(range(len(sizes)), key=lambda i: -sizes[i][1]):
        w, h = sizes[i]
        if w > MAX or h > MAX:
            raise SystemExit(f"a sheet of {w}x{h} does not fit a {MAX} page")
        if x + w > MAX:
            x, y, row = 0, y + row, 0
        if y + h > MAX:
            page, x, y, row = page + 1, 0, 0, 0
        out[i] = (page, x, y); x += w; row = max(row, h)
    return out


def build(character: str) -> dict:
    d = EXPORT / character
    clips = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json")) if not p.name.startswith("_")}
    groups = [[c for c in g if c in clips] for g in GROUPS.get(character, [[]])]
    rest = [c for c in clips if not any(c in g for g in groups)]
    if rest:
        groups[-1] += rest
    pages, manifest, n0 = [], {"format": "workbench-atlas/1", "character": character, "pages": [], "clips": {}}, 0
    for gi, g in enumerate(groups):
        if not g:
            continue
        imgs = {c: Image.open(d / clips[c]["image"]).convert("RGBA") for c in g}
        place = shelf([imgs[c].size for c in g])
        for c, (p, x, y) in zip(g, place):
            pg = n0 + p
            while len(pages) <= pg:
                pages.append([])
            pages[pg].append((c, x, y, imgs[c]))
            manifest["clips"][f"{character}/{c}"] = {"page": pg, "offset": [x, y], "group": "core" if gi == 0 else f"group{gi}", "json": clips[c]}
        n0 = len(pages)
    for i, items in enumerate(pages):
        W = max(x + im.width for _, x, _, im in items); H = max(y + im.height for _, _, y, im in items)
        page = Image.new("RGBA", (W, H))
        for _, x, y, im in items:
            page.alpha_composite(im, (x, y))
        name = f"_atlas_{i}.png"; page.save(d / name, optimize=True)
        manifest["pages"].append({"image": name, "size": [W, H], "clips": [f"{character}/{c}" for c, *_ in items],
                                  "group": manifest["clips"][f"{character}/{items[0][0]}"]["group"]})
    (d / "_atlas.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def main():
    for c in sorted(p.name for p in EXPORT.iterdir() if p.is_dir()):
        m = build(c)
        print(f"{c}: {len(m['clips'])} clips on {len(m['pages'])} page(s): " +
              "; ".join(f"{p['image']} {p['size'][0]}x{p['size'][1]} ({p['group']}: {len(p['clips'])} clips)" for p in m["pages"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
