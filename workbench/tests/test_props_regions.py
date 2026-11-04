"""Props geometry/checks and per-region identity on synthetic frames."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze as A  # noqa: E402
import props as P  # noqa: E402
import regions as R  # noqa: E402
from test_metrics import blank, rect  # noqa: E402

LEDGE = {"floor_y": 500.0, "anchor": [0, 0], "path": {"type": "line", "from": [0, 0], "to": [0, 0]},
         "props": [{"type": "ledge", "id": "L", "front_x": 300, "back_x": 600, "top_y": 400, "cap": {"overhang": 0, "thickness": 0}}]}


def test_surfaces_and_distance():
    s = P.surfaces(LEDGE)
    kinds = {x["kind"] for x in s}
    assert {"ground", "ledge_top", "ledge_face"} <= kinds
    d, sf = P.nearest_surface((350, 395), s)
    assert sf["kind"] == "ledge_top" and d == pytest.approx(5)
    d, sf = P.nearest_surface((350, 395), s, "ground")   # floor under the ledge is not a surface
    assert d > 50


def test_clip_and_support_on_a_box_figure():
    img = blank(); rect(img, 280, 300, 320, 420)   # overlaps the front face by 20px: a near limb, allowed
    f = P.frame_checks(img, (0, 0), LEDGE, P.surfaces(LEDGE), P.solids(LEDGE), None)
    assert f["clip_px"] == 0 and f["allowed_overlap"]["in_front_of_face_px"] > 0
    img = blank(); rect(img, 380, 300, 420, 430)   # sinks 30px through the top, well behind the front: clipping
    f = P.frame_checks(img, (0, 0), LEDGE, P.surfaces(LEDGE), P.solids(LEDGE), None)
    assert f["clip_px"] > 0 and f["clip_depth"] >= 10
    hand = {"hand_r": {"x": 400, "y": 408, "state": "planted", "surface": "ledge_top"}}  # fingers 8px over the edge
    f = P.frame_checks(blank(), (0, 0), LEDGE, P.surfaces(LEDGE), P.solids(LEDGE), hand)
    assert f["contacts"][0]["dist"] <= f["contacts"][0]["tol"] and not f["contacts"][0]["in_solid"]
    img2 = blank(); rect(img2, 100, 300, 140, 500)  # standing on the floor (rows up to 499)
    f2 = P.frame_checks(img2, (0, 0), LEDGE, P.surfaces(LEDGE), P.solids(LEDGE), None)
    assert f2["clip_px"] == 0 and "floor" in f2["touching"]


def test_contact_off_surface_and_contact_path():
    contacts = [{"hand_r": {"x": 350, "y": 380, "state": "planted", "surface": "ledge_top"}}]
    f = P.frame_checks(blank(), (0, 0), LEDGE, P.surfaces(LEDGE), P.solids(LEDGE), contacts[0])
    assert f["contacts"][0]["dist"] == pytest.approx(20)
    offs, _ = P.contact_path(LEDGE, contacts, [(0.0, 0.0)])
    assert offs[0][1] == pytest.approx(20)  # moved down 20 so the hand is on the top


def test_regions_reference_scores_one_and_detects_recolour():
    ref = blank(); rect(ref, 100, 100, 200, 200, (200, 40, 40)); rect(ref, 100, 200, 200, 400, (40, 40, 200))
    model = R.learn(ref, {"top": [150, 150], "bottom": [150, 300]})
    m = R.measure(ref, model)
    assert m["top"]["share_ratio"] == pytest.approx(1) and m["top"]["de"] == pytest.approx(0, abs=1e-3)
    other = ref.copy(); other[100:200, 100:200, :3] = (200, 90, 40)   # top recoloured past tolerance
    m2 = R.measure(other, model)
    assert m2["top"]["share"] < 0.1 * model["top"]["ref_share"]
    small = blank(); rect(small, 100, 100, 200, 150, (200, 40, 40)); rect(small, 100, 150, 200, 400, (40, 40, 200))
    assert R.measure(small, model)["top"]["share_ratio"] < 0.7
