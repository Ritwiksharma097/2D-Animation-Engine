"""Mechanics sandbox: getting caught + retry, and a full win (apple, cover, throw, guard eats, climb, key, exit)."""
import subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402


def main(base_url=None, shot_prefix="9"):
    port = free_port()
    srv = None
    if not base_url:
        srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port), "--no-prepare"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1); base_url = f"http://127.0.0.1:{port}/sandbox/index.html"
    fails = 0
    def check(name, ok, detail=""):
        nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + str(detail)[:160])
    try:
        with sync_playwright() as p:
            br = launch(p); page = br.new_page(viewport={"width": 1240, "height": 820})
            errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(base_url); page.wait_for_selector("body[data-ready='1']")
            box = page.locator("#cv").bounding_box(); k = box["width"] / 1200
            click = lambda x, y: page.mouse.click(box["x"] + x * k, box["y"] + y * k)
            idle = lambda t=30000: page.wait_for_function("!sb.ren.busy || sb.game.state !== 'play'", timeout=t)
            # 1) walk at the guard: caught, then retry
            click(560, 460)
            page.wait_for_function("sb.game.state === 'caught'", timeout=45000)
            page.wait_for_timeout(900); page.screenshot(path=str(SHOTS / f"{shot_prefix}0_sandbox_caught.png"))
            check("walking into his view gets Ren caught", page.evaluate("sb.ren.clip.key") == "ren/caught_game_over", page.locator("#hud").inner_text())
            check("HUD names non-approved animations", "NOT OWNER-APPROVED" in page.locator("#hud").inner_text())
            page.wait_for_selector("#retry:not([hidden])", timeout=5000); page.locator("#retry").click()
            check("retry resets", page.evaluate("sb.game.state") == "play" and abs(page.evaluate("sb.ren.x") - 80) < 1)
            # 2) win: apple, cover, throw left, sneak right while he eats, climb, key, out the back
            click(200, 461); page.wait_for_function("sb.I.inventory.has('apple')", timeout=20000); idle()
            check("picked up the apple at the interact pickup event", True, page.locator("#msg").inner_text())
            click(340, 460); idle()
            check("in cover: guard can't see Ren", page.evaluate("!sb.brain.last.seen"), page.evaluate("sb.brain.last.reason"))
            # the bush itself blocks sight: a guard at 560 facing Ren (in the bush) within range
            r = page.evaluate("""(() => { const g = sb.guard, x = g.x, d = g.dir; g.x = 560; g.dir = -1; const r = sb.brain.look(sb.ren); g.x = x; g.dir = d; return r.reason + ' ' + (r.by || ''); })()""")
            check("the bush blocks his line of sight", r.startswith("blocked") and "bush" in r, r)
            page.locator("#throw").click(); click(60, 460)
            page.wait_for_function("sb.brain.state.mode === 'eating'", timeout=25000)
            page.screenshot(path=str(SHOTS / f"{shot_prefix}1_sandbox_distracted.png"))
            check("thrown apple distracts him: he walks to it and eats", True, page.evaluate("sb.brain.state.mode"))
            click(900, 366); page.wait_for_function("sb.I.inventory.has('key') || sb.game.state !== 'play'", timeout=40000)
            check("climbed and took the key", page.evaluate("sb.I.inventory.has('key')"), page.locator("#hud").inner_text())
            idle(); page.screenshot(path=str(SHOTS / f"{shot_prefix}2_sandbox_key.png"))
            click(1160, 460); page.wait_for_function("sb.game.state !== 'play'", timeout=40000)
            check("got out with the key", page.evaluate("sb.game.state") == "won", page.evaluate("sb.game.state"))
            page.screenshot(path=str(SHOTS / f"{shot_prefix}3_sandbox_won.png"))
            check("no page errors", not errs, errs)
            br.close()
    finally:
        if srv: srv.terminate()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:2])))
