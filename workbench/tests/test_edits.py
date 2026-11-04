"""Edit-layer tests on synthetic frames."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze as A  # noqa: E402
import edits as E  # noqa: E402
from test_metrics import GROUND, blank, figure, rect  # noqa: E402


def doc(frames, **kw):
    return {"format": "workbench-action/1", "frames": frames, **kw}


def test_order_drop_hold_and_durations():
    src = {"a.png": figure(200, 400), "b.png": figure(220, 380), "c.png": figure(240, 360)}
    d = doc([{"file": "c.png", "duration_ms": 100}, {"file": "a.png", "duration_ms": 50, "hold": 3},
             {"file": "b.png", "drop": True}])
    out = E.apply(d, src, list(src), GROUND)
    assert [f.file for f in out] == ["c.png", "a.png"]
    assert [f.duration_ms for f in out] == [100, 150]
    assert [f.entry for f in out] == [0, 1]


def test_offset_moves_image_and_contacts():
    img = rect(blank(), 100, 100, 110, 120)
    d = doc([{"file": "a.png", "offset": [5, -7], "contacts": {"foot_l": {"x": 105, "y": 119, "state": "planted"}}}])
    f = E.apply(d, {"a.png": img}, ["a.png"], GROUND)[0]
    ys, xs = np.nonzero(f.image[..., 3])
    assert (xs.min(), ys.min()) == (105, 93)
    assert (f.contacts["foot_l"]["x"], f.contacts["foot_l"]["y"]) == (110, 112)


def test_snap_uses_planted_foot_then_lowest_pixel():
    img = rect(blank(), 100, 100, 110, 520)  # lowest pixel 519
    with_foot = doc([{"file": "a.png", "contacts": {"heel_l": {"x": 105, "y": 515, "state": "planted"}}}], snap_to_ground=True)
    f = E.apply(with_foot, {"a.png": img}, ["a.png"], GROUND)[0]
    assert f.dy == GROUND - 515 and f.contacts["heel_l"]["y"] == GROUND
    f = E.apply(doc([{"file": "a.png"}], snap_to_ground=True), {"a.png": img}, ["a.png"], GROUND)[0]
    assert f.dy == GROUND - 519 and E.lowest_pixel(f.image) == GROUND


def test_mirror_flips_image_and_contacts():
    img = rect(blank(), 10, 100, 20, 120)
    d = doc([{"file": "a.png", "contacts": {"foot_l": {"x": 15, "y": 119, "state": "planted"}}}], mirror=True)
    f = E.apply(d, {"a.png": img}, ["a.png"], GROUND)[0]
    xs = np.nonzero(f.image[..., 3].any(axis=0))[0]
    w = img.shape[1]
    assert (xs.min(), xs.max()) == (w - 20, w - 11)
    assert f.contacts["foot_l"]["x"] == w - 1 - 15


def test_suggest_holds_groups_consecutive_duplicates():
    frames = [figure(200, 400), figure(201, 400), figure(200, 401), figure(240, 360, lift_front=40), figure(241, 360, lift_front=40)]
    files = [f"{i:02d}.png" for i in range(1, 6)]
    s = E.suggest_holds(frames, files, A.TH["duplicate"], base_ms=100, calm=2, min_ms=250, max_ms=1500)
    kept = [e for e in s if not e.get("drop")]
    assert [(e["file"], e["hold"]) for e in kept] == [("01.png", 3), ("04.png", 2)]
    assert kept[0]["hold"] * kept[0]["duration_ms"] == pytest.approx(600)
    assert kept[1]["hold"] * kept[1]["duration_ms"] == pytest.approx(400)
    assert sum(1 for e in s if e.get("drop")) == 3
