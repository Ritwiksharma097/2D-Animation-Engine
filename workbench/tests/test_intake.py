"""Intake on synthetic sheets: figures found in reading order, detached effects kept, scaled and grounded."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import intake as I  # noqa: E402


def sheet(white=True):
    """6 figures in 2 rows, uneven spacing; figure 3 has a detached 'sparkle' above its head."""
    a = np.zeros((420, 900, 4), np.uint8)
    if white:
        a[...] = (255, 255, 255, 255)
    xs = [30, 170, 320, 470, 640, 780]
    for k, x in enumerate(xs):
        y0 = 20 if k < 3 else 230
        body = (40 + 20 * k, 60, 140, 255)
        a[y0 + 30:y0 + 180, x:x + 50] = body                  # body 150 px tall
        a[y0:y0 + 30, x + 10:x + 40] = (230, 180, 140, 255)    # head
        if k == 2:
            a[y0 - 12:y0 - 4, x + 60:x + 68] = (250, 220, 0, 255)  # detached effect
    return a


def test_components_find_figures_in_order_and_keep_effects():
    figs = I.split_components(I.to_rgba(Image.fromarray(sheet(), "RGBA").convert("RGB")))
    assert len(figs) == 6
    colours = [tuple(f[f.shape[0] - 5, f.shape[1] // 3, :3]) for f in figs]   # body colour encodes the index
    assert [c[0] for c in colours] == [40 + 20 * k for k in range(6)]
    assert any(f.shape[0] >= 180 + 10 for f in figs[2:3])  # figure 3 includes its sparkle (taller box)


def test_grid_and_place_on_ground():
    a = np.zeros((420, 900, 4), np.uint8)
    for k in range(6):                       # one figure per 300x210 cell
        x, y0 = (k % 3) * 300 + 120, (k // 3) * 210 + 15
        a[y0 + 30:y0 + 180, x:x + 50] = (90, 60, 140, 255); a[y0:y0 + 30, x + 10:x + 40] = (230, 180, 140, 255)
    figs = I.split_grid(a, 3, 2)
    assert len(figs) == 6
    out, info = I.place(figs[0], 2.0, (640, 576), 535, 320)
    ys, xs = np.nonzero(out[..., 3] > 128)
    assert ys.max() == 535                          # lowest pixel on the ground line
    assert abs((ys.max() - ys.min() + 1) - 360) <= 2  # 180 px figure scaled x2
    assert not info["clipped_by_cell"]
