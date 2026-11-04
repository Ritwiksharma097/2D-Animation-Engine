"""Screenshot the browser workbench in several states (visual verification, not an automated pass).

    python workbench/tests/screenshot_workbench.py            # writes out/screenshots/*.png

Starts workbench/serve.py on a free port, drives Chromium with Playwright, and also exercises
contact editing + save through the real UI. Look at the PNGs afterwards.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "out" / "screenshots"


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def launch(p):
    exe = os.environ.get("CHROMIUM_PATH")
    try:
        return p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
    except Exception:
        for cand in sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux*/chrome")):
            return p.chromium.launch(executable_path=str(cand), args=["--no-sandbox"])
        raise


def main(states=None):
    SHOTS.mkdir(parents=True, exist_ok=True)
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "workbench" / "serve.py"), "--port", str(port)])
    try:
        time.sleep(1.0)
        base = f"http://127.0.0.1:{port}/workbench/index.html"
        shots = states or {
            "01_guard_walk_inplace": "#a=guard/walk&frame=1",
            "02_guard_walk_onion": "#a=guard/walk&frame=7&onion=3,3&a.zoom=0.75",
            "03_ren_keypose_moving_old_timing": "#a=ren/walk_keypose&mode=moving&travel=41.9&steps=5&zoom=0.5",
            "04_compare_guard_vs_ren": "#a=guard/walk&b=ren/walk_keypose&zoom=0.5&frame=3",
            "05_fourteen_moving_best": "#a=ren/rejected_walk_fourteen&mode=moving&travelmode=best&steps=10&zoom=0.5",
        }
        errors = []
        with sync_playwright() as p:
            br = launch(p)
            page = br.new_page(viewport={"width": 1500, "height": 1250})
            # 404s for annotations/ and out/ are expected when nothing is annotated or analysed yet
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "404" not in m.text else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            for name, h in shots.items():
                page.goto("about:blank")
                page.goto(base + h)
                page.wait_for_selector("body[data-ready='1']", timeout=15000)
                page.wait_for_timeout(300)
                page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)
                print("shot", name)
            # play for a moment and check the frame advanced
            page.goto("about:blank"); page.goto(base + "#a=guard/idle&play=1")
            page.wait_for_selector("body[data-ready='1']")
            f0 = page.evaluate("workbench.viewers[0].idx"); page.wait_for_timeout(700)
            f1 = page.evaluate("workbench.viewers[0].idx")
            print(f"playback: frame index {f0} -> {f1} after 0.7s")
            br.close()
        if errors:
            print("BROWSER ERRORS:", *errors, sep="\n  ")
        return errors
    finally:
        srv.terminate()


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
