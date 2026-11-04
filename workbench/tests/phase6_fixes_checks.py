"""Step 29: proximity + bodies, the caught rule (meter), loading when img.decode() never resolves, shared page setup on
every demo page (DPR + taps), and the hub page."""
import subprocess, sys, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402

HANG_DECODE = "HTMLImageElement.prototype.decode = function () { return new Promise(() => {}); };"   # as in a window that isn't drawn
PAGES = {"sandbox": "sandbox/index.html", "play": "out/export/play.html", "guard_demo": "out/export/guard_demo.html", "level_play": "out/export/level_play.html"}


def main():
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port), "--no-prepare"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1); base = f"http://127.0.0.1:{port}"
    fails = 0
    def check(name, ok, detail=""):
        nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + str(detail)[:170])
    try:
        with sync_playwright() as p:
            br = launch(p)
            # --- loading never hangs, sharp canvas and taps on every demo page
            ctx = br.new_context(viewport={"width": 1000, "height": 760}, device_scale_factor=2)
            ctx.add_init_script(HANG_DECODE)
            for name, path in PAGES.items():
                pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e, errs=errs: errs.append(str(e)))
                pg.goto(f"{base}/{path}")
                try:
                    pg.wait_for_selector("body[data-ready='1']", timeout=20000); ready = True
                except Exception:
                    ready = False
                check(f"{name}: loads although img.decode() never resolves", ready and pg.locator(".preload").count() == 0, errs)
                if not ready:
                    pg.close(); continue
                css, back = pg.evaluate("[document.getElementById('cv').getBoundingClientRect().width, document.getElementById('cv').width]")
                check(f"{name}: canvas is 2x its CSS width at DPR 2 (shared runtime/page.js)", abs(back - 2 * css) <= 2, f"css {css:.0f} backing {back}")
                box = pg.locator("#cv").bounding_box(); k = box["width"] / 1200
                tap = lambda x, y: pg.mouse.click(box["x"] + x * k, box["y"] + y * k)
                if name == "play":
                    x0 = pg.evaluate("playtest.ren.x"); tap(300, 460); pg.wait_for_timeout(1500)
                    check("play: a tap walks Ren", pg.evaluate("playtest.ren.x") != x0)
                elif name == "guard_demo":
                    tap(900, 370); pg.wait_for_timeout(300)
                    check("guard_demo: a tap drops food", pg.evaluate("!!demo.food"))
                elif name == "level_play":
                    tap(300, 460); pg.wait_for_timeout(300)
                    check("level_play: a tap plans a route", pg.evaluate("!!lp.last && lp.last.ok"), pg.evaluate("lp.last && lp.last.reason"))
                pg.screenshot(path=str(SHOTS / f"96_{name}_dpr2.png"))
                pg.close()
            ctx.close()

            # --- sandbox rules
            page = br.new_page(viewport={"width": 1240, "height": 860}); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
            def fresh():
                page.goto(f"{base}/sandbox/index.html"); page.wait_for_selector("body[data-ready='1']")
            fresh()
            need = page.evaluate("sb.brain.cfg.suspicion.caught_at / sb.brain.cfg.suspicion.rise_per_s")
            hud = page.locator("#hud").inner_text()
            check("HUD shows the suspicion meter and the rule", "suspicion [" in hud and "caught when full" in hud, hud.splitlines()[2] if len(hud.splitlines()) > 2 else hud)
            # plain sight on the floor, Ren standing still in front of him
            page.evaluate("""(() => { const g = sb.guard; g.clear(); g.next(); g.x = 560; g.dir = 1; sb.ren.clear(); sb.ren.x = 760; })()""")
            t0 = time.time(); page.wait_for_function("sb.game.state === 'caught'", timeout=int((need + 3) * 1000)); dt = time.time() - t0
            check(f"plain sight on the floor ends in a catch (meter needs {need:.2f} s)", True, f"caught after {dt:.2f} s")
            # plain sight on the ledge he can't climb: still a catch (the owner's escape case)
            fresh()
            page.evaluate("""(() => { const g = sb.guard, r = sb.ren; g.clear(); g.next(); g.x = 640; g.dir = 1;
                                       r.clear(); r.surface = 'L1'; r.y = sb.world.surfaceY('L1'); r.x = 880; })()""")
            page.wait_for_timeout(500); page.screenshot(path=str(SHOTS / "97_sandbox_meter_ledge.png"))
            t0 = time.time()
            try:
                page.wait_for_function("sb.game.state === 'caught'", timeout=int((need + 3) * 1000)); ok = True
            except Exception:
                ok = False
            check("plain sight on the ledge (out of his reach) ends in a catch", ok, f"after {time.time() - t0 + 0.5:.2f} s, sight {page.evaluate('sb.brain.last.reason')}")
            # standing right behind him: he hears, turns and catches
            fresh()
            page.evaluate("""(() => { const g = sb.guard, r = sb.ren; g.clear(); g.next(); g.x = 600; g.dir = 1; r.clear(); r.x = 560; })()""")
            page.wait_for_function("sb.guard.dir === -1", timeout=4000)
            check("Ren standing just behind him is heard: the guard turns round", True, page.evaluate("sb.brain.last.reason + ' heard=' + sb.brain.last.heard"))
            page.wait_for_function("sb.game.state === 'caught'", timeout=8000)
            check("...and then catches him", True)
            # bodies: Ren walks into the guard (guard standing, facing away) and stops instead of passing through
            fresh()
            page.evaluate("""(() => { const g = sb.guard, r = sb.ren; g.clear(); g.next(); g.x = 640; g.dir = 1; sb.brain.cfg.patrol = [640, 640];
                                       r.x = 420; r.dir = 1; r.walkTo(900); })()""")
            page.wait_for_function("sb.brain.last.bumped || sb.game.state !== 'play'", timeout=5000)
            page.wait_for_timeout(300); page.screenshot(path=str(SHOTS / "98_sandbox_bump.png"))
            gap, rr = page.evaluate("[sb.guard.x - sb.ren.x, sb.T.bodies.ren_radius + sb.T.bodies.guard_radius]")
            check("Ren can't walk through the guard: stops within one stride of touching", rr - 1 <= gap < rr + 48 and page.evaluate("sb.ren.x < sb.guard.x"),
                  f"gap {gap:.0f} px (radii sum {rr}, Ren's stride ~47)")
            page.wait_for_function("sb.game.state === 'caught'", timeout=6000)
            check("the bump is noticed: he turns, sees Ren close in front and catches him", True, page.evaluate("sb.brain.last.reason"))
            check("no page errors", not errs, errs)
            # --- hub
            hub = br.new_page(); hub.goto(f"{base}/"); hub.wait_for_selector("body[data-ready='1']")
            check("/ redirects to the hub", hub.url.endswith("/workbench/hub.html"), hub.url)
            links = hub.eval_on_selector_all("a", "as => as.map(a => a.href)")
            bad = []
            for u in links:
                try:
                    urllib.request.urlopen(u, timeout=10)
                except Exception as e:
                    bad.append(f"{u} {e}")
            check("every hub link resolves", not bad and len(links) >= 12, f"{len(links)} links; bad {bad}")
            check("hub lists the redraw spec sheets", hub.locator("#specs a").count() >= 3, hub.locator("#specs").inner_text())
            hub.screenshot(path=str(SHOTS / "99_hub.png"), full_page=True)
            br.close()
    finally:
        srv.terminate()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
