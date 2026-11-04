"""Level playtest (routing + camera) and level editor (transition colours, drag a height, save)."""
import json, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402


def main():
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port), "--no-prepare"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1); fails = 0
    test_level = ROOT / "levels" / "test_editor_check.json"
    def check(name, ok, detail):
        nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + str(detail)[:150])
    try:
        with sync_playwright() as p:
            br = launch(p); page = br.new_page(viewport={"width": 1300, "height": 760})
            errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/out/export/level_play.html"); page.wait_for_selector("body[data-ready='1']")
            box = page.locator("#cv").bounding_box(); k = box["width"] / 1200
            def click_world(x, y):
                cx = page.evaluate("lp.cam.x"); page.mouse.click(box["x"] + (x - cx) * k, box["y"] + y * k)
            idle = lambda t=40000: page.wait_for_function("!lp.ren.busy", timeout=t)
            click_world(600, 360); page.wait_for_timeout(300); idle()
            check("route onto the 94 px ledge", page.evaluate("lp.ren.surface") == "L1", page.locator("#msg").inner_text())
            click_world(900, 460); idle()
            check("down the back face", page.evaluate("lp.ren.surface") == "A#1", page.locator("#msg").inner_text())
            while page.evaluate("lp.cam.x") + 1150 < 1440:   # walk right until the far floor scrolls into view
                click_world(min(1280, page.evaluate("lp.cam.x") + 1150), 460); idle()
            click_world(page.evaluate("lp.cam.x") + 1150, 460)   # a point on the far floor
            page.wait_for_function("lp.ren.state === 'jump'", timeout=40000); page.screenshot(path=str(SHOTS / "80_level_jump.png")); idle()
            click_world(page.evaluate("lp.cam.x") + 1100, 460); idle()
            cam = page.evaluate("lp.cam.x")
            check("jump the gap; camera follows", page.evaluate("lp.ren.surface") == "B#0" and cam > 400, f"surface {page.evaluate('lp.ren.surface')}, camera {cam:.0f}")
            while page.evaluate("lp.ren.x") < 1750:   # walk on until the platform and the wall are on screen
                click_world(min(1800, page.evaluate("lp.cam.x") + 1100), 460); idle()
            click_world(2050, 290); page.wait_for_timeout(300)
            check("platform behind the ladder refused for Ren", "refused" in page.locator("#msg").inner_text() and "ladder" in page.locator("#msg").inner_text(), page.locator("#msg").inner_text())
            click_world(2420, 290); page.wait_for_timeout(300)
            check("170 px wall refused", "refused" in page.locator("#msg").inner_text(), page.locator("#msg").inner_text())
            page.screenshot(path=str(SHOTS / "81_level_refused.png"))
            # editor
            page.goto(f"http://127.0.0.1:{port}/workbench/level_editor.html"); page.wait_for_selector("body[data-ready='1']")
            ok_before = page.evaluate("ed.edges.filter(e => e.platform === 'L1' && e.type === 'climb_up').every(e => e.ok)")
            page.screenshot(path=str(SHOTS / "82_editor.png"))
            box = page.locator("#cv").bounding_box(); k = page.evaluate("document.querySelector('#cv').width / ed.level.size[0]") * box["width"] / page.evaluate("document.querySelector('#cv').width")
            x, y = box["x"] + 600 * k, box["y"] + 376 * k
            page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x, y - 40 * k); page.mouse.move(x, y - 80 * k); page.mouse.up()
            top = page.evaluate("ed.level.ledges.find(l => l.id === 'L1').top")
            red = page.evaluate("ed.edges.filter(e => e.platform === 'L1' && e.type === 'climb_up').every(e => !e.ok)")
            check("dragging L1's top 80 px higher turns its climbs red", ok_before and red and abs(top - 296) <= 2, f"top {top}, before ok {ok_before}, now red {red}")
            page.screenshot(path=str(SHOTS / "83_editor_too_high.png"))
            page.locator("#name").fill("test_editor_check"); page.locator("#save").click(); page.wait_for_timeout(600)
            saved = json.loads(test_level.read_text()) if test_level.exists() else {}
            check("save writes the level JSON", saved.get("ledges", [{}])[0].get("top") == top, page.locator("#msg").inner_text())
            check("no page errors", not errs, errs)
            br.close()
    finally:
        srv.terminate(); test_level.unlink(missing_ok=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
