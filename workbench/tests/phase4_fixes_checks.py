"""Step 18 checks: review page makes no 404 requests, shows the preparing banner, character scales editable;
playtest characters start apart and the stage fills the width. Restores _settings.json."""
import json, shutil, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402

SET = ROOT / "annotations/_settings.json"


def main():
    before = SET.read_text(encoding="utf-8")
    # force background preparation: remove two reports (one edited action)
    for d in ("out/guard/happy", "out/guard/idle"):
        shutil.rmtree(ROOT / d, ignore_errors=True)
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.6); fails = 0
    def check(name, ok, detail):
        nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + detail)
    try:
        with sync_playwright() as p:
            br = launch(p); page = br.new_page(viewport={"width": 1300, "height": 1000})
            bad = []; page.on("response", lambda r: bad.append(r.url) if r.status >= 400 else None)
            errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/workbench/review.html"); page.wait_for_selector("body[data-ready='1']", timeout=60000)
            banner = page.locator("#banner")
            shown = banner.is_visible() and "Preparing" in banner.inner_text()
            check("preparing banner while reports are made", shown, banner.inner_text()[:90] if shown else "not shown")
            page.screenshot(path=str(SHOTS / "60_review_preparing.png"))
            page.wait_for_function("document.querySelector('#banner').style.display === 'none'", timeout=240000)
            page.wait_for_timeout(2500); page.wait_for_selector("body[data-ready='1']")
            ba = page.locator("section.card", has_text="guard/idle").first.locator(".ba img").count()
            check("before/after appears after preparation (no reload)", ba == 1, f"{ba} before/after image(s) on guard/idle")
            check("no 404/error responses", not bad, f"{len(bad)} bad: {bad[:3]}")
            g = page.locator(".charset", has_text="guard")
            check("guard scale shown as unconfirmed", "UNCONFIRMED" in g.inner_text(), g.inner_text()[:80])
            g.locator("input[type=number]").fill("0.52"); g.locator("button").click()
            page.wait_for_function("[...document.querySelectorAll('.charset .msg')].some(m => m.textContent.startsWith('saved'))")
            saved = json.loads(SET.read_text())["characters"]["guard"]
            check("scale saved to _settings.json", saved["game_scale"] == 0.52 and not saved["confirmed"], str(saved))
            gw = None
            for _ in range(120):   # background re-export (runs the ledge sweeps, ~20-60 s)
                time.sleep(1)
                try:
                    gw = json.loads((ROOT / "out/export/guard/walk.json").read_text())["scale"]
                except (ValueError, OSError):
                    continue
                if gw == 0.52:
                    break
            check("playtest re-exported with the new scale", gw == 0.52, f"guard export scale {gw}")
            page.screenshot(path=str(SHOTS / "61_review_ready.png"))
            page.goto(f"http://127.0.0.1:{port}/out/export/play.html"); page.wait_for_selector("body[data-ready='1']")
            pos = page.evaluate("[playtest.ren.x, playtest.guard.x]")
            check("Ren and the guard start apart", abs(pos[0] - pos[1]) > 150, f"ren {pos[0]}, guard {pos[1]}")
            w = page.evaluate("[document.querySelector('#cv').getBoundingClientRect().width, innerWidth]")
            check("stage fills the width", w[0] > 0.95 * w[1] - 40, f"canvas {w[0]:.0f}px of {w[1]}px")
            page.screenshot(path=str(SHOTS / "62_play_start.png"))
            check("no page errors", not errs, "; ".join(errs) or "none")
            br.close()
    finally:
        srv.terminate()
        SET.write_text(before, encoding="utf-8")
        subprocess.run([sys.executable, str(ROOT / "workbench/export.py"), "--demo"], stdout=subprocess.DEVNULL)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
