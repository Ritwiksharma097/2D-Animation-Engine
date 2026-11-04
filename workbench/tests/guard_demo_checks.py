"""Guard demo on the runtime: drop food behind him, he turns, walks, eats (pickup/bite events), returns to patrol."""
import subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402


def main():
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port), "--no-prepare"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1); fails = 0
    def check(name, ok, detail):
        nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + detail)
    try:
        with sync_playwright() as p:
            br = launch(p); page = br.new_page(viewport={"width": 1240, "height": 600})
            errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/out/export/guard_demo.html"); page.wait_for_selector("body[data-ready='1']")
            page.wait_for_function("demo.guard.state === 'walk'", timeout=15000)
            page.wait_for_timeout(1500)
            g = page.evaluate("[demo.guard.x, demo.guard.dir]")
            fx = g[0] - g[1] * 250              # behind him
            box = page.locator("#cv").bounding_box(); k = box["width"] / 1200
            page.mouse.click(box["x"] + fx * k, box["y"] + 300 * k)
            page.wait_for_function("demo.guard.state === 'turn' || demo.guard.dir !== %d" % g[1], timeout=5000)
            check("turns toward food behind him", True, f"food at {fx:.0f}, guard at {g[0]:.0f} facing {g[1]}")
            page.wait_for_function("demo.guard.state === 'play'", timeout=20000)
            page.wait_for_timeout(250); page.screenshot(path=str(SHOTS / "70_guard_demo_eat.png"))
            page.wait_for_function("demo.food === null", timeout=5000)
            log = page.locator("#log").inner_text()
            check("pickup event removed the prop", "pickup" in log, log)
            page.wait_for_function("document.querySelector('#log').textContent.includes('back to patrol')", timeout=8000)
            check("bite event fired", "bite" in page.locator("#log").inner_text(), page.locator("#log").inner_text())
            page.wait_for_function("demo.guard.state === 'walk'", timeout=15000)
            check("returns to patrol", True, page.evaluate("demo.guard.state"))
            check("no page errors", not errs, "; ".join(errs) or "none")
            br.close()
    finally:
        srv.terminate()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
