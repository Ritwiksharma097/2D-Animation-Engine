"""A synthetic walk drawn exactly to the guard spec must meet its measurable criteria; a shuffle must not."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze as A  # noqa: E402
import spec_check as SC  # noqa: E402
import specs as SP  # noqa: E402


def draw(spec, frames_spec, H):
    out = []
    g = int(spec["ground_y"])
    for k, fs in enumerate(frames_spec):
        img = np.zeros((576, 640, 4), np.uint8)
        hip = int(fs["hip_y"])
        img[g - int(H):hip, 270:350] = (90, 90, 140, 255)                      # body, its top fixed so height stays even
        for name, c in fs["contacts"].items():
            x, y = int(c["x"]), int(c["y"])
            img[y - 18:y + 1, x - 22:x + 22] = (60, 40, 30, 255)                 # boot (planted ones sit on the ground)
            img[hip:y - 18, x - 8:x + 8] = (50, 50, 50, 255)                     # leg from hip to boot
        out.append(img)
    return out


def test_synthetic_walk_meets_spec_and_shuffle_misses(tmp_path):
    frames_spec, S, v = SP.walk_targets(414, 310, 535)
    spec = {"character": "guard", "ground_y": 535, "travel_px_per_frame": v, "frames": frames_spec,
            "criteria": {**SP.walk_criteria(8, v, S, 535), "no_flags": ["stance_not_moving", "slide_unavoidable"]}}
    good = tmp_path / "good"; good.mkdir()
    for k, img in enumerate(draw(spec, frames_spec, 414)):
        Image.fromarray(img).save(good / f"{k + 1:02d}.png")
    act = SC.load_folder(good, spec, v)
    res = {r["criterion"]: r for r in SC.evaluate(spec, act, A.analyze(act))}
    slide = next(r for k, r in res.items() if k.startswith("slide at"))
    assert slide["meets"], slide
    assert res["steps per loop = 2"]["meets"]
    assert next(r for k, r in res.items() if k.startswith("planted feet"))["meets"]
    # the same 8 frames but every frame = frame 1 (shuffling in place) must miss
    bad = tmp_path / "bad"; bad.mkdir()
    for k in range(8):
        Image.open(good / "01.png").save(bad / f"{k + 1:02d}.png")
    act = SC.load_folder(bad, spec, v)
    res = {r["criterion"]: r for r in SC.evaluate(spec, act, A.analyze(act))}
    assert not res["distinct poses = 8"]["meets"]
    assert not next(r for k, r in res.items() if k.startswith("slide at"))["meets"]
