"""Identity regions page: click to move a seed, add a region, save, check an action. Restores _identity.json."""
import json, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402

F = ROOT / "annotations/ren/_identity.json"


def main():
    before = F.read_text(encoding="utf-8")
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port), "--no-prepare"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1); fails = 0
    def check(name, ok, detail):
        nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + detail)
    try:
        with sync_playwright() as p:
            br = launch(p); page = br.new_page(viewport={"width": 1300, "height": 1100})
            errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/workbench/regions.html#c=ren"); page.wait_for_selector("body[data-ready='1']")
            n0 = page.locator("#tbl tbody tr").count()
            check("existing regions loaded", n0 == len(json.loads(before)["regions"]), f"{n0} rows")
            to_canvas = lambda x, y: page.evaluate(f"""(() => {{ const r = document.querySelector('#cv').getBoundingClientRect();
                 return [r.left + ({x} - box.x0) * k * r.width / cv.width, r.top + ({y} - box.y0) * k * r.height / cv.height]; }})()""")
            page.locator("#tbl tbody tr", has_text="hood").click()
            x, y = to_canvas(325, 150); page.mouse.click(x, y)
            seed = page.evaluate("regions.hood.seed")
            check("click moves the selected seed", abs(seed[0] - 325) <= 2 and abs(seed[1] - 150) <= 2, f"hood seed {seed}")
            page.locator("#newname").fill("belt"); page.locator("#add").click()
            x, y = to_canvas(319, 300); page.mouse.click(x, y)
            page.screenshot(path=str(SHOTS / "50_regions_edit.png"), full_page=True)
            page.locator("#save").click(); page.wait_for_function("document.querySelector('#msg').textContent.startsWith('saved')")
            saved = json.loads(F.read_text())["regions"]
            check("saved to _identity.json", "belt" in saved and saved["hood"]["seed"] == seed, f"{sorted(saved)}")
            page.locator("#action").select_option("jump"); page.locator("#check").click()
            page.wait_for_selector("#result img", timeout=60000); page.wait_for_timeout(800)
            rows = page.locator("#result tr").count() - 1
            check("check shows every saved region", rows == len(saved), f"{rows} rows for {len(saved)} regions")
            page.screenshot(path=str(SHOTS / "51_regions_check_jump.png"), full_page=True)
            check("no page errors", not errs, "; ".join(errs) or "none")
            br.close()
    finally:
        srv.terminate()
        F.write_text(before, encoding="utf-8")   # leave the real seeds unchanged
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
