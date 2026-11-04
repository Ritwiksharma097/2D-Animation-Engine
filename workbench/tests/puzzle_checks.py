"""Step 32: objects with state (lever, gate, lamp, chest, locked door), item use, conditions, save / restore / reset
(sandbox/puzzle.html)."""
import subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402


def main(base_url=None):
    port = free_port(); srv = None
    if not base_url:
        srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port), "--no-prepare"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1); base_url = f"http://127.0.0.1:{port}/sandbox/puzzle.html"
    fails = 0
    def check(name, ok, detail=""):
        nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + str(detail)[:170])
    try:
        with sync_playwright() as p:
            br = launch(p); page = br.new_page(viewport={"width": 1240, "height": 800}); errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(base_url); page.evaluate("localStorage.clear()"); page.reload(); page.wait_for_selector("body[data-ready='1']")
            ev = page.evaluate
            def tap(x, y=440):
                box = page.locator("#cv").bounding_box(); k = box["width"] / 1200
                page.mouse.click(box["x"] + x * k, box["y"] + y * k)
            done = lambda: page.wait_for_function("!pz.ren.busy && !pz.pending", timeout=20000)
            msg = lambda: page.locator("#msg").inner_text()
            def use(x):
                tap(x); page.wait_for_timeout(200); done(); page.wait_for_timeout(150)
            check("the level's puzzle data has no lint problems", "no problems" in page.locator("#hud").inner_text(), ev("pz.lint"))
            use(420); check("the gate won't open by hand (explicit rule)", "lever" in msg(), msg())
            use(780); check("the chest is out of reach behind the closed gate (a blocking door)", "can't reach" in msg() and ev("pz.ren.x") < 420, f"{msg()} x {ev('pz.ren.x'):.0f}")
            use(150); check("the lever opens the gate", ev("pz.st.states.lever1") == "on" and ev("pz.st.states.gate") == "open", ev("JSON.stringify(pz.st.states)"))
            page.screenshot(path=str(SHOTS / "c0_puzzle_lever.png"))
            use(780); check("the chest is too dark to open while the lamp is off (condition)", "dark" in msg() and ev("pz.st.states.chest") == "closed", msg())
            use(600); check("the lamp turns on", ev("pz.st.states.lamp") == "on")
            use(780); check("the chest opens and gives the key", ev("pz.st.inventory.includes('key')") and ev("pz.st.states.chest") == "open", msg())
            page.screenshot(path=str(SHOTS / "c1_puzzle_key.png"))
            use(1000); check("the door is locked", "locked" in msg(), msg())
            # reload: everything restored from localStorage
            x_before = ev("pz.ren.x"); page.reload(); page.wait_for_selector("body[data-ready='1']")
            check("reload restores states, inventory and Ren's position", ev("pz.st.states.chest") == "open" and ev("pz.st.inventory.includes('key')") and abs(ev("pz.ren.x") - x_before) < 1,
                  f"{msg()} | {ev('JSON.stringify(pz.st)')[:110]}")
            page.locator("#inv button", has_text="key").click(); use(1000)
            check("using the key on the door unlocks it and uses the key up", ev("pz.st.states.door") == "closed" and not ev("pz.st.inventory.includes('key')"), msg())
            use(1000); check("then the door opens", ev("pz.st.states.door") == "open")
            tap(1150); done(); page.wait_for_function("pz.won", timeout=10000)
            check("through the door to the exit: solved", True, msg()); page.screenshot(path=str(SHOTS / "c2_puzzle_solved.png"))
            page.locator("#reset").click(); page.wait_for_timeout(200)
            check("reset starts a fresh room and clears the save", ev("pz.st.states.door") == "locked" and ev("pz.st.inventory.length") == 0 and ev("pz.ren.x") == 60
                  and ev("localStorage.getItem('workbench.puzzle_room.v1') === null || JSON.parse(localStorage.getItem('workbench.puzzle_room.v1')).state.states.door === 'locked'"))
            check("no page errors", not errs, errs)
            br.close()
    finally:
        if srv: srv.terminate()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:2])))
