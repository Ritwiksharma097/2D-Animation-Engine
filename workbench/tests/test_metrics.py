"""Metric tests on synthetic frames: rectangles with known geometry and motion."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze as A  # noqa: E402

W, H, GROUND = 640, 576, 535


def blank():
    return np.zeros((H, W, 4), np.uint8)


def rect(img, x0, y0, x1, y1, rgb=(200, 80, 40)):
    img[y0:y1, x0:x1, :3] = rgb
    img[y0:y1, x0:x1, 3] = 255
    return img


def figure(back_x, front_x, lift_front=0, body_dx=0):
    """Body block plus two 40px-wide 'feet' whose bottoms sit on GROUND (front foot optionally lifted)."""
    f = blank()
    rect(f, 260 + body_dx, 150, 360 + body_dx, 470, (60, 120, 60))
    rect(f, back_x, GROUND - 15, back_x + 40, GROUND + 1, (90, 60, 40))
    rect(f, front_x, GROUND - 15 - lift_front, front_x + 40, GROUND + 1 - lift_front, (90, 60, 40))
    # legs joining the body so the figure is one shape above the foot band
    rect(f, back_x + 10, 470, back_x + 30, GROUND - 15, (40, 40, 40))
    rect(f, front_x + 10, 470, front_x + 30, GROUND - 15 - lift_front, (40, 40, 40))
    return f


def make_action(frames, travel=None, loop="once", name="walk"):
    return A.Action(character="test", action=name, files=[Path(f"{i:02d}.png") for i in range(len(frames))],
                    frames=frames, durations_ms=[100] * len(frames), loop_mode=loop, ground_y=GROUND,
                    travel=travel, travel_source="test" if travel is not None else "none", is_walk=True)


def test_geometry_bbox_and_baseline():
    g = A.figure_geometry(figure(200, 400))
    assert g["bbox"] == [200, 150, 439, GROUND]
    assert g["baseline"] == GROUND
    assert g["height"] == GROUND - 150 + 1


def test_pose_distance_identity_and_shift():
    a = figure(200, 400)
    assert A.frame_distance(a, a) == 0
    b = figure(200, 400, body_dx=40)
    assert 0.1 < A.frame_distance(a, b) < 1


def test_near_duplicate_and_out_of_order():
    poses = [figure(200, 400), figure(220, 380), figure(240, 360, lift_front=40), figure(201, 400)]
    d = A.distance_matrix(poses)
    ch = A.change_analysis(d, loop=False, is_walk=False)
    assert any({i, j} == {0, 3} for i, j, _ in ch["near_duplicates"])
    assert ch["distinct_drawings"] == 3
    # frame 4 (index 3) resembles frame 1 more than its neighbour frame 3
    assert any(i == 3 and j == 0 for i, j, *_ in ch["out_of_order"])


def test_foot_clusters_planted_and_lifted():
    fc = A.foot_clusters(figure(200, 400, lift_front=0))
    assert len(fc["clusters"]) == 2 and all(c["planted"] for c in fc["clusters"])
    assert fc["clusters"][0]["x"] == pytest.approx(219.5, abs=0.6)
    lifted = A.foot_clusters(figure(200, 400, lift_front=30))
    assert [c["planted"] for c in lifted["clusters"]] == [True, False]  # lifted foot still in band, not planted


def synthetic_walk(v=10, n=6):
    """Back foot planted and moving back v px per frame (as a stance foot does); front foot swinging forward."""
    return [figure(back_x=300 - k * v, front_x=420 + k * v) for k in range(n)]


def test_slide_zero_at_matching_travel():
    act = make_action(synthetic_walk(10), travel=10)
    w = A.walk_analysis(act, [A.foot_clusters(f) for f in act.frames])
    assert all(s == pytest.approx(0, abs=0.01) for s in w["slide_per_step_px"])


def test_slide_equals_speed_error():
    act = make_action(synthetic_walk(10), travel=16)
    w = A.walk_analysis(act, [A.foot_clusters(f) for f in act.frames])
    assert all(s == pytest.approx(6, abs=0.01) for s in w["slide_per_step_px"])
    assert w["slide_total_px"] == pytest.approx(6 * 5, abs=0.1)


def test_recommended_travel_matches_stance_motion():
    rec = A.best_constant_travel([[12.0, -30.0]] * 5, vmax=60)
    assert rec == pytest.approx(12.0, abs=0.25)
    rec = A.best_constant_travel([[12.0, -30.0]] * 5, vmax=60, vmin=20)
    assert rec == pytest.approx(20.0, abs=0.25)


def test_walk_in_place_has_no_backward_stance():
    frames = [figure(250, 380) for _ in range(6)]
    assert A.best_constant_travel([[0.0]] * 5, vmax=50) == 0.0
    act = make_action(frames, travel=10)
    w = A.walk_analysis(act, [A.foot_clusters(f) for f in act.frames])
    assert w["slide_total_px"] == pytest.approx(50, abs=0.1)


def test_annotation_contacts_used_and_named():
    frames = synthetic_walk(10, 3)
    ann = {"frames": [{"file": f"{i:02d}.png", "contacts": {
        "foot_l": {"x": 300 - 7 * i, "y": GROUND, "state": "planted"},
        "foot_r": {"x": 440 + 10 * i, "y": GROUND - 20, "state": "free"}}} for i in range(3)]}
    act = make_action(frames, travel=7)
    act.annotations = ann
    w = A.walk_analysis(act, [A.foot_clusters(f) for f in frames])
    assert w["contact_source"] == "annotations"
    assert w["slide_per_step_px"] == [pytest.approx(0), pytest.approx(0)]
    assert w["recommended_per_frame_travel_px"] == [pytest.approx(7), pytest.approx(7)]


def test_stride_segments_counts_steps():
    lows, highs = A.stride_segments([200, 190, 80, 150, 210, 200, 90, 160], loop=True)
    assert len(lows) == 2 and len(highs) == 2
    lows, _ = A.stride_segments([200, 80, 200, 80, 200, 80], loop=True)
    assert len(lows) == 3


def test_palette_identical_frame_has_zero_distance():
    f = figure(200, 400)
    centres = A.palette(f, k=3)
    s1, s2 = A.palette_stats(f, centres), A.palette_stats(f, centres)
    assert 0.5 * np.abs(s1["hist"] - s2["hist"]).sum() == pytest.approx(0)
    assert s1["mean_de"] < 1.0


def _ann_walk():
    """3 frames; heel_l planted 0->1 (moves back 9px), toe_l planted 1->2 (moves back 5px), nothing shared 2->0."""
    return {"frames": [
        {"file": "00.png", "contacts": {"heel_l": {"x": 300, "y": GROUND, "state": "planted"}}},
        {"file": "01.png", "contacts": {"heel_l": {"x": 291, "y": GROUND, "state": "planted"},
                                        "toe_l": {"x": 330, "y": GROUND, "state": "planted"}}},
        {"file": "02.png", "contacts": {"toe_l": {"x": 325, "y": GROUND, "state": "planted"},
                                        "heel_r": {"x": 420, "y": GROUND - 30, "state": "free"}}},
    ]}


def test_from_contacts_travel_cannot_slide_where_contacts_are_shared():
    frames = synthetic_walk(10, 3)
    act = make_action(frames, loop="loop")
    act.annotations, act.travel_mode = _ann_walk(), "from_contacts"
    w = A.walk_analysis(act, [A.foot_clusters(f) for f in frames])
    assert w["travel_used_per_step_px"][:2] == [pytest.approx(9), pytest.approx(5)]
    assert w["slide_per_step_px"][:2] == [pytest.approx(0), pytest.approx(0)]
    assert w["steps_without_shared_contact"] == [[2, 0]]
    assert w["travel_used_per_step_px"][2] == pytest.approx(7)  # mean fills the step with no shared contact


def test_named_contacts_use_worst_shared_contact():
    # two contacts planted in both frames, moving back 10 and 4: at travel 10 the second slides 6
    ca = [{"name": "heel_l", "x": 300, "planted": True}, {"name": "toe_l", "x": 340, "planted": True}]
    cb = [{"name": "heel_l", "x": 290, "planted": True}, {"name": "toe_l", "x": 336, "planted": True}]
    ds = A.step_pairs(ca, cb, 1.0, named=True)
    assert sorted(ds) == [4, 10]
    assert A.slide_for_travel([ds], 10, named=True) == [pytest.approx(6)]
    assert A.slide_for_travel([ds], 10, named=False) == [pytest.approx(0)]


def test_per_frame_travel_list():
    act = make_action(synthetic_walk(10), travel=[10, 10, 4, 10, 10])
    act.travel_mode = "per_frame"
    w = A.walk_analysis(act, [A.foot_clusters(f) for f in act.frames])
    assert w["slide_per_step_px"] == [pytest.approx(0), pytest.approx(0), pytest.approx(6), pytest.approx(0), pytest.approx(0)]
