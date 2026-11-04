"""Step 30: parallax layers, a foreground occluder drawn over Ren, depth sorting, a hiding spot the guard walks past,
and doors between two screens with a fade (sandbox/scenes.html)."""
import subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402


def main(base_url=None):
    port = free_port(); srv = None
    if not base_url:
        srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port), "--no-prepare"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1); base_url = f"http://127.0.0.1:{port}/sandbox/scenes.html"
    fails = 0
    def check(name, ok, detail=""):
        nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + str(detail)[:170])
    try:
        with sync_playwright() as p:
            br = launch(p); page = br.new_page(viewport={"width": 1240, "height": 820}); errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(base_url); page.wait_for_selector("body[data-ready='1']")
            box = page.locator("#cv").bounding_box(); k = box["width"] / 1200
            ev = page.evaluate
            def tap(wx, wy):   # world coordinates -> screen, through the camera
                cam = ev("sd.S.cam.x"); page.mouse.click(box["x"] + (wx - cam) * k, box["y"] + wy * k)
            def pixel(wx, wy):  # canvas pixel at a world point (backing store coordinates)
                return ev(f"""(() => {{ const c = document.getElementById('cv'), s = c.width / 1200, x = Math.round(({wx} - sd.S.cam.x) * s), y = Math.round({wy} * s);
                                      return Array.from(c.getContext('2d').getImageData(x, y, 1, 1).data); }})()""")
            # keep the guard out of the way while testing layers
            ev("(() => { const g = sd.S.guard; g.clear(); g.next(); g.x = 1450; g.dir = 1; sd.S.brain.cfg.patrol = [1450, 1450]; })()")
            page.screenshot(path=str(SHOTS / "a0_scene_start.png"))
            # occluder: walk Ren behind the pillar; the pillar's grey covers his body
            tap(585, 460); page.wait_for_function("!sd.S.ren.busy", timeout=15000)
            rx = ev("sd.S.ren.x"); px = pixel(585, 380)
            check("Ren stands at the pillar", 560 <= rx <= 610, f"x {rx:.0f}")
            check("the pillar is drawn in front of Ren (grey over his body)", abs(px[0] - 140) < 20 and abs(px[1] - 140) < 20 and abs(px[2] - 140) < 20, px)
            page.screenshot(path=str(SHOTS / "a1_scene_pillar.png"))
            # parallax: walk right, the camera scrolls and far layers move less than the world
            tap(900, 460); page.wait_for_function("!sd.S.ren.busy", timeout=20000); page.wait_for_timeout(1500)
            cam = ev("sd.S.cam.x")
            check("the camera follows Ren into the wider screen", cam > 40, f"cam x {cam:.0f}")
            far = ev("sd.S.scene.layers.find(l => l.id === 'far_hills').parallax"); near = ev("sd.S.scene.layers.find(l => l.id === 'near_hills').parallax")
            check("layers have parallax factors far < near < world < foreground", far < near < 1 < ev("sd.S.scene.layers.find(l => l.id === 'front_grass').parallax"), f"{far} {near}")
            page.screenshot(path=str(SHOTS / "a2_scene_parallax.png"))
            # hide behind the crate, then let the guard patrol past it
            tap(1025, 430); page.wait_for_function("sd.S.ren.holding", timeout=15000)
            page.wait_for_function("!!sd.S.ren.hidingIn", timeout=3000); page.wait_for_timeout(100)
            check("Ren holds the placeholder crouch behind the crate and is hidden", ev("sd.S.ren.hidingIn && sd.S.ren.hidingIn.id") == "crate",
                  page.locator("#hud").inner_text().splitlines()[1])
            check("HUD labels the crouch as a placeholder", "PLACEHOLDER crouch" in page.locator("#hud").inner_text())
            check("the crate is drawn over Ren (depth sort)", pixel(1025, 440)[:3] != [255, 255, 255] and abs(pixel(1025, 440)[0] - 122) < 30, pixel(1025, 440))
            page.screenshot(path=str(SHOTS / "a3_scene_hidden.png"))
            ev("(() => { const b = sd.S.brain; b.cfg.patrol = [820, 1450]; window.MAXS = 0; window.SEENCLOSE = 0;"
               " setInterval(() => { MAXS = Math.max(MAXS, b.state.suspicion || 0); if (b.last.seen) SEENCLOSE = Math.max(SEENCLOSE, 1); }, 30); })()")
            page.wait_for_function("sd.S.guard.x < 900", timeout=25000)
            page.wait_for_timeout(500)
            check("the guard walks past the hiding spot without catching Ren", not ev("sd.S.over"), f"max suspicion {ev('MAXS'):.2f}")
            check("...but he does see him while very close (reveal radius)", ev("SEENCLOSE") == 1, f"reveal radius {ev('sd.S.scene.hiding[0].reveal_radius')} px")
            page.screenshot(path=str(SHOTS / "a4_scene_guard_passed.png"))
            # door: tap it, fade, screen B
            ev("(() => { const g = sd.S.guard; g.clear(); g.next(); g.x = 820; g.dir = -1; sd.S.brain.cfg.patrol = [820, 820]; })()")   # out of the way
            tap(1340, 460); page.wait_for_function("!sd.S.ren.busy", timeout=20000); tap(1560, 460)
            page.wait_for_function("!sd.S.ren.busy && sd.S.cam.x > 560", timeout=20000)
            tap(1730, 420)
            page.wait_for_function("sd.fader.alpha > 0.3", timeout=20000)
            page.screenshot(path=str(SHOTS / "a5_scene_fade.png"))
            page.wait_for_function("sd.S.name === 'scene_b' && !sd.fader.busy", timeout=5000)
            check("the door leads to screen B through a fade", True, f"Ren at x {ev('sd.S.ren.x'):.0f} on {ev('sd.S.ren.surface')}")
            page.screenshot(path=str(SHOTS / "a6_scene_b.png"))
            tap(70, 420); page.wait_for_function("sd.S.name === 'scene_a' && !sd.fader.busy", timeout=20000)
            check("and back to screen A at the other door", abs(ev("sd.S.ren.x") - 1650) < 2, f"x {ev('sd.S.ren.x'):.0f}")
            ev("sd.enter('scene_b', 400)"); tap(1140, 420); page.wait_for_function("sd.S.over", timeout=20000)
            check("the exit on screen B ends the run", "exit" in page.locator("#msg").inner_text(), page.locator("#msg").inner_text())
            check("no page errors", not errs, errs)
            br.close()
    finally:
        if srv: srv.terminate()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:2])))
