"""Scene-mode screenshots + a live edit of the ledge height (needs serve.py; started here)."""
import subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402


def main():
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    base = f"http://127.0.0.1:{port}/workbench/index.html"
    ok = True
    try:
        with sync_playwright() as p:
            br = launch(p); page = br.new_page(viewport={"width": 1500, "height": 1300})
            errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
            for name, h in {"20_scene_ren_climb_up_f4": "#a=ren/climb_up&mode=scene&frame=4",
                            "21_scene_ren_climb_up_f10": "#a=ren/climb_up&mode=scene&frame=10",
                            "22_scene_guard_climb_up_f7": "#a=guard/climb_up&mode=scene&frame=7",
                            "23_scene_guard_ladder_f4": "#a=guard/ladder_up&mode=scene&frame=4"}.items():
                page.goto("about:blank"); page.goto(base + h); page.wait_for_selector("body[data-ready='1']")
                page.wait_for_timeout(500); page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True); print("shot", name)
            # live edit: raise Ren's ledge from 197 to 260 px; the frame-10 hand must go further off the top
            page.goto("about:blank"); page.goto(base + "#a=ren/climb_up&mode=scene&frame=10"); page.wait_for_selector("body[data-ready='1']")
            get = "workbench.viewers[0].sceneRes.frames[9].contacts.find(c => c.name === 'hand_r').dist"
            before = page.evaluate(get)
            v = page.locator("section.viewer").first
            v.locator(".s-height").fill("260"); v.locator(".s-height").dispatch_event("change"); page.wait_for_timeout(2500)
            after = page.evaluate(get)
            ok = after > before + 50
            print(("PASS" if ok else "FAIL"), f"live ledge edit: hand_r frame 10 distance {before} -> {after} px")
            page.screenshot(path=str(SHOTS / "24_scene_ledge_260.png"), full_page=True)
            if errs: print("page errors:", errs); ok = False
            br.close()
    finally:
        srv.terminate()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
