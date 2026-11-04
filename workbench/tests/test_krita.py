"""Krita pack -> (simulated drawing + Krita render names) -> intake --as-is reproduces every frame exactly."""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analyze as A  # noqa: E402
import intake as I  # noqa: E402
import krita_export as K  # noqa: E402


def test_pack_layout_and_round_trip(tmp_path):
    out, meta = K.pack("ren", "walk_keypose", "specs/ren_walk_inbetweens.json", tmp_path / "pack")
    assert [f["kind"] for f in meta["frames"]] == ["keep", "draw"] * 4
    for sub in ("frames", "targets", "onion", "ghost"):
        files = sorted((out / sub).glob("*.png"))
        assert len(files) == 8 and all(Image.open(f).size == (640, 576) for f in files)
    assert (out / "KRITA_STEPS.md").exists() and "--as-is" in (out / "KRITA_STEPS.md").read_text()
    # "artist": fill each blank frame with the previous key shifted half way, render as Krita names frame_0000.png...
    render = tmp_path / "render"; render.mkdir()
    frames = [np.array(Image.open(f)) for f in sorted((out / "frames").glob("*.png"))]
    for k, f in enumerate(frames):
        if f[..., 3].max() == 0:
            f = K.shift_x(frames[k - 1], -22)
        Image.fromarray(f, "RGBA").save(render / f"frame_{k:04d}.png")
    dest_name = "krita_roundtrip_test"
    try:
        reg, rep = I.intake(render, "ren", dest_name, replaces="walk_keypose", images=False, as_is=True)
        back = sorted((I.INCOMING / "ren" / dest_name).glob("[0-9][0-9].png"))
        assert len(back) == 8
        for k, f in enumerate(back):
            assert np.array_equal(np.array(Image.open(f)), np.array(Image.open(render / f"frame_{k:04d}.png"))), f"frame {k + 1} changed"
        assert reg["scale"] == 1.0 and reg["alignment"].startswith("as drawn")
    finally:
        shutil.rmtree(I.INCOMING / "ren" / dest_name, ignore_errors=True)
        shutil.rmtree(A.OUT / "incoming" / "ren" / dest_name, ignore_errors=True)
        for d in (I.INCOMING / "ren", A.OUT / "incoming" / "ren"):
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
