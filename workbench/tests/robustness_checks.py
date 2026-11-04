"""Step 27: build dist/, serve it with a plain static server (no serve.py), and check the sandbox there:
preload progress, crisp canvas at devicePixelRatio 2, a touch tap walks Ren, hidden tab pauses, plus the full sandbox run."""
import subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402
import sandbox_checks  # noqa: E402

sys.path.insert(0, str(ROOT / "workbench"))
import build_dist  # noqa: E402


def main():
    dist = ROOT / "dist"
    build_dist.build(dist)
    port = free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "-d", str(dist)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    url = f"http://127.0.0.1:{port}/sandbox/index.html"
    fails = 0
    def check(name, ok, detail=""):
        nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + str(detail)[:160])
    try:
        with sync_playwright() as p:
            br = launch(p)
            # crisp rendering at DPR 2, and touch input
            ctx = br.new_context(viewport={"width": 900, "height": 700}, device_scale_factor=2, has_touch=True, is_mobile=True)
            page = ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(url); page.wait_for_selector("body[data-ready='1']")
            check("preload bar finished and removed itself", page.locator(".preload").count() == 0)
            css_w, back_w = page.evaluate("[document.getElementById('cv').getBoundingClientRect().width, document.getElementById('cv').width]")
            check("canvas backing store is 2x its CSS width at DPR 2", abs(back_w - 2 * css_w) <= 2, f"css {css_w:.0f} backing {back_w}")
            box = page.locator("#cv").bounding_box(); k = box["width"] / 1200
            x0 = page.evaluate("sb.ren.x")
            page.touchscreen.tap(box["x"] + 450 * k, box["y"] + 460 * k)
            page.wait_for_function(f"sb.ren.x > {x0} + 20", timeout=10000)
            check("a touch tap walks Ren (logical coordinates at DPR 2)", True, f"x {x0:.0f} -> {page.evaluate('sb.ren.x'):.0f}")
            page.wait_for_timeout(500); page.screenshot(path=str(SHOTS / "94_dist_sandbox_dpr2_touch.png"))
            # pause when hidden: fake the visibility state, positions must freeze
            page.evaluate("Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange'))")
            a = page.evaluate("[sb.ren.x, sb.guard.x]"); page.wait_for_timeout(1200); b = page.evaluate("[sb.ren.x, sb.guard.x]")
            check("hidden tab pauses the simulation", a == b, f"{a} -> {b}")
            page.evaluate("Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange'))")
            page.wait_for_timeout(800); c = page.evaluate("[sb.ren.x, sb.guard.x]")
            check("visible again: it resumes without a jump", c != b and abs(c[1] - b[1]) < 120, f"{b} -> {c}")
            check("no page errors", not errs, errs)
            ctx.close()
            idx = br.new_page(); idx.goto(f"http://127.0.0.1:{port}/index.html")
            check("dist index links the demos", idx.locator("a").count() == 7, idx.locator("a").all_inner_texts())
            for href in ["out/export/play.html", "out/export/guard_demo.html", "out/export/level_play.html"]:
                pg = br.new_page(); e = []; pg.on("pageerror", lambda x, e=e: e.append(str(x)))
                bad = []; pg.on("response", lambda r, bad=bad: bad.append(r.url) if r.status >= 400 else None)
                pg.goto(f"http://127.0.0.1:{port}/{href}"); pg.wait_for_timeout(2500)
                check(f"{href} runs from the static build", not e and not bad, e + bad)
                pg.close()
            br.close()
        print("-- full sandbox run against dist/ --")
        fails += sandbox_checks.main(url, shot_prefix="95")
    finally:
        srv.terminate()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
