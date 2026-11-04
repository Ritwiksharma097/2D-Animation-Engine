"""Drive out/export/play.html through every playtest feature and assert the results. Screenshots to out/screenshots/."""
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402


def main():
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port), "--no-prepare"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1); fails = 0
    url = f"http://127.0.0.1:{port}/out/export/play.html"
    try:
        with sync_playwright() as p:
            br = launch(p); page = br.new_page(viewport={"width": 1240, "height": 720})
            errs = []; page.on("pageerror", lambda e: errs.append(str(e)))

            def check(name, ok, detail):
                nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + detail)

            def fresh():
                page.goto("about:blank"); page.goto(url); page.wait_for_selector("body[data-ready='1']")
            ev = lambda js: page.evaluate(js)
            fresh()
            box = page.locator("#cv").bounding_box(); k = box["width"] / 1200
            click = lambda x, y: page.mouse.click(box["x"] + x * k, box["y"] + y * k)
            wait_idle = lambda t=20000: page.wait_for_function("playtest.ren.act === 'idle'", timeout=t)

            check("idle drawing while standing", ev("playtest.ren.name") == "ren/idle", ev("playtest.ren.name"))
            click(380, 450); page.wait_for_timeout(600); page.screenshot(path=str(SHOTS / "30_play_walk.png")); wait_idle()
            r = ev("[playtest.ren.x, playtest.ren.maxDrift]")
            check("walk right with contact travel does not slide", r[1] < 0.01 and r[0] > 300, f"x={r[0]:.0f}, max drift {r[1]:.2f} game px")
            click(150, 450); page.wait_for_function("playtest.ren.act === 'walk'"); page.wait_for_timeout(500)
            dirn = ev("playtest.ren.dir"); page.screenshot(path=str(SHOTS / "35_play_walk_left.png")); wait_idle()
            r = ev("[playtest.ren.x, playtest.ren.maxDrift]")
            check("walk left is mirrored and does not slide", dirn == -1 and r[1] < 0.01 and r[0] < 200, f"dir {dirn}, x={r[0]:.0f}, drift {r[1]:.2f}")
            page.check("#oldTiming"); click(380, 450); wait_idle()
            check("old constant travel slides", ev("playtest.ren.maxDrift") > 5, f"max drift {ev('playtest.ren.maxDrift'):.1f} game px")
            page.uncheck("#oldTiming")
            L = ev("[LEDGE.x0, LEDGE.top, LEDGE.x1]")
            click(L[0] + 2, 455); wait_idle()
            fr = ev("playtest.ren.x") + ev("""(() => { const w = playtest.A['ren/walk_keypose']; return Math.max(...w.frames.map(f => f.offset[0] + f.rect[2] - w.anchor[0])) * w.scale; })()""")
            check("floor walk stops before the ledge face", fr <= L[0] + 40 * 0.4777 + 0.5, f"front-most pixel {fr:.0f}, face {L[0]:.0f}")
            click(L[0] + 80, L[1] - 30); page.wait_for_function("playtest.ren.act === 'climb'")
            page.wait_for_function("playtest.ren.k >= 9", timeout=5000); page.screenshot(path=str(SHOTS / "31_play_climb.png")); wait_idle()
            s = ev("[playtest.ren.surface, playtest.ren.y, LEDGE.top]")
            check("climb up ends on the ledge", s[0] == "ledge" and abs(s[1] - s[2]) < 1, f"{s[0]}, y {s[1]:.1f} vs {s[2]:.1f}")
            F = ev("[FAR.x0, FAR.top]")
            click(F[0] + 120, F[1] - 30); page.wait_for_function("playtest.ren.act === 'jump'")
            page.wait_for_function("playtest.ren.k >= 5", timeout=5000); page.screenshot(path=str(SHOTS / "32_play_jump.png"))
            jy = ev("playtest.ren.y"); wait_idle()
            s = ev("[playtest.ren.surface, playtest.ren.x, FAR.x0, playtest.A['ren/jump'].jump.air_frames]")
            check("jump (timing from the export) lands on the far platform", s[0] == "far" and s[1] > s[2] and jy < F[1] - 10,
                  f"{s[0]}, x {s[1]:.0f}; air frames {s[3]} from the export; mid-air y {jy:.0f} above top {F[1]:.0f}")
            click(L[0] + 100, L[1] - 30); wait_idle()
            check("jump back to the ledge", ev("playtest.ren.surface") == "ledge", ev("playtest.ren.surface"))
            click(150, 450); page.wait_for_function("playtest.ren.name === 'ren/climb_down'", timeout=20000)
            page.wait_for_function("playtest.ren.k >= 7", timeout=5000); page.screenshot(path=str(SHOTS / "36_play_climb_down.png")); wait_idle()
            s = ev("[playtest.ren.surface, playtest.ren.y, playtest.ren.x]")
            check("climb down ends on the floor and walks on", s[0] == "floor" and abs(s[1] - 470) < 1 and s[2] < 200, f"{s[0]}, y {s[1]:.1f}, x {s[2]:.0f}")
            # guard patrols: he moves, his idle holds play, and his (rejected) walk drifts
            g0 = ev("playtest.guard.x"); page.wait_for_timeout(9000)
            g = ev("[playtest.guard.x, playtest.guard.maxDrift, playtest.guard.name]")
            check("guard patrols on the same floor", abs(g[0] - g0) > 30 or g[2] == "guard/walk", f"x {g0:.0f} -> {g[0]:.0f}, now {g[2]}")
            check("guard's walk shows drift (his drawings walk in place)", g[1] > 1, f"max drift {g[1]:.1f} game px")
            page.screenshot(path=str(SHOTS / "37_play_guard_pins.png"))
            page.uncheck("#pins"); page.wait_for_timeout(200)
            check("toggle hides pins and drift", page.locator("#drift").inner_text().strip() == "", repr(page.locator("#drift").inner_text()))
            page.check("#pins")
            # ledge height
            fresh()
            page.locator("#ledgeH").fill("70"); page.locator("#ledgeH").dispatch_event("input")
            check("70% marked unsupported", "NOT supported" in page.locator("#ledgeMsg").text_content(), page.locator("#ledgeMsg").text_content()[:70])
            L = ev("[LEDGE.x0, LEDGE.top]")
            click(L[0] + 80, L[1] - 30); page.wait_for_function("playtest.ren.act === 'climb'", timeout=20000)
            page.wait_for_function("playtest.ren.k >= 4", timeout=5000); page.screenshot(path=str(SHOTS / "34_play_ledge70.png")); wait_idle()
            s = ev("[playtest.ren.surface, playtest.ren.y, LEDGE.top]")
            check("climb at 70% ends on that ledge", s[0] == "ledge" and abs(s[1] - s[2]) < 1, f"y {s[1]:.1f} vs top {s[2]:.1f}")
            check("no page errors", not errs, "; ".join(errs) or "none")
            br.close()
    finally:
        srv.terminate()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
