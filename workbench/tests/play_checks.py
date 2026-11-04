"""Drive out/export/play.html: walk (no slide), old timing (slides), climb, jump. Screenshots to out/screenshots/."""
import subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402


def main():
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1); fails = 0
    try:
        with sync_playwright() as p:
            br = launch(p); page = br.new_page(viewport={"width": 1240, "height": 700})
            errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/out/export/play.html"); page.wait_for_selector("body[data-ready='1']")
            box = page.locator("#cv").bounding_box(); k = box["width"] / 1200
            click = lambda x, y: page.mouse.click(box["x"] + x * k, box["y"] + y * k)
            wait_idle = lambda t=15000: page.wait_for_function("playtest.ren.act === 'idle'", timeout=t)
            def check(name, ok, detail):
                nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + detail)
            click(380, 450); page.wait_for_timeout(700); page.screenshot(path=str(SHOTS / "30_play_walk.png"))
            wait_idle()
            r = page.evaluate("[playtest.ren.x, playtest.ren.maxDrift]")
            check("walk with contact travel does not slide", r[1] < 0.01 and r[0] > 300, f"x={r[0]:.0f}, max planted drift {r[1]:.2f} game px")
            page.check("#oldTiming"); click(130, 450); wait_idle()
            d = page.evaluate("playtest.ren.maxDrift")
            check("old constant travel slides", d > 5, f"max drift {d:.1f} game px at 41.9 cell px/drawing")
            page.uncheck("#oldTiming")
            # walking at the ledge must stop before the face (the phase-2 bug)
            L = page.evaluate("[LEDGE.x0, LEDGE.top]")
            click(L[0] + 2, 455); wait_idle()
            fr = page.evaluate("""(() => { const w = playtest.A.walk_keypose, r = playtest.ren;
                return Math.max(...w.frames.map(f => f.offset[0] + f.rect[2] - w.anchor[0])) * w.scale + r.x; })()""")
            band = page.evaluate("40 * playtest.A.walk_keypose.scale")
            check("floor walk stops before the ledge face", fr <= L[0] + band + 0.5, f"front-most walk pixel at {fr:.0f}, face at {L[0]:.0f} (+{band:.0f} allowed)")
            pop = page.evaluate("playtest.ren.climbStart - playtest.ren.x")
            print(f"  note: climb starts {pop:.0f} game px ahead of where the walk stops")
            click(L[0] + 80, L[1] - 30); page.wait_for_function("playtest.ren.act === 'climb'", timeout=15000)
            page.wait_for_function("playtest.ren.k >= 9", timeout=5000); page.screenshot(path=str(SHOTS / "31_play_climb.png"))
            wait_idle()
            s = page.evaluate("[playtest.ren.surface, playtest.ren.y, LEDGE.top]")
            check("climb ends on the ledge", s[0] == "ledge" and abs(s[1] - s[2]) < 1, f"surface {s[0]}, y {s[1]:.1f} vs ledge top {s[2]:.1f}")
            F = page.evaluate("[FAR.x0, FAR.top]")
            click(F[0] + 120, F[1] - 30); page.wait_for_function("playtest.ren.act === 'jump'", timeout=15000)
            page.wait_for_function("playtest.ren.k >= 5", timeout=5000); page.screenshot(path=str(SHOTS / "32_play_jump.png"))
            wait_idle()
            s = page.evaluate("[playtest.ren.surface, playtest.ren.x, FAR.x0]")
            check("jump lands on the far platform", s[0] == "far" and s[1] > s[2], f"surface {s[0]}, x {s[1]:.0f} (platform from {s[2]:.0f})")
            page.screenshot(path=str(SHOTS / "33_play_end.png"))
            check("no page errors", not errs, "; ".join(errs) or "none")
            br.close()
    finally:
        srv.terminate()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
