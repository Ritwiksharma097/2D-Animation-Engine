"""Step 34: the two-screen sandbox played through in the level runner (sandbox/run.html?level=two_a): hide from the guard,
take the key, unlock and open the gate, go through the door, the arrival sequence with emotes on screen 2, get out.
Plus: being seen ends in a catch and retry restores the screen; progress survives a reload; validation is clean.
The guard is never moved by the test: it waits for him, as a player would."""
import subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402


def main(base_url=None):
    port = free_port(); srv = None
    if not base_url:
        srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port), "--no-prepare"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1); base_url = f"http://127.0.0.1:{port}/sandbox/run.html"
    fails = 0
    def check(name, ok, detail=""):
        nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + str(detail)[:200])
    try:
        with sync_playwright() as p:
            br = launch(p); page = br.new_page(viewport={"width": 1240, "height": 860}); errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(base_url + "?level=two_a&fresh=1"); page.evaluate("localStorage.removeItem('workbench.runner.v1')")
            page.goto(base_url + "?level=two_a&fresh=1"); page.wait_for_selector("body[data-ready='1']")
            ev = page.evaluate
            def tap(wx, wy=440):
                box = page.locator("#cv").bounding_box(); k = box["width"] / 1200; cam = ev("rn.S.cam.x")
                page.mouse.click(box["x"] + (wx - cam) * k, box["y"] + wy * k)
            def reach(wx):   # walk right until a world x is on screen (a player scrolls the same way)
                for _ in range(4):
                    if wx - ev("rn.S.cam.x") <= 1150 or ev("rn.S.over"): return
                    tap(ev("rn.S.cam.x") + 1100, 455)
                    page.wait_for_function(f"rn.S.cam.x > {wx - 1150} || !rn.S.ren.busy || rn.S.over", timeout=20000); page.wait_for_timeout(300)
            settle = lambda t=20000: page.wait_for_function("!rn.S.ren.busy && !rn.S.pending && !rn.S.seqs.running", timeout=t)
            guard = lambda: ev("[Math.round(rn.S.guards[0].x), rn.S.guards[0].dir, rn.S.brains[0].state.mode, +(rn.S.brains[0].state.suspicion||0).toFixed(2)]")
            check("screen 1 has no level problems", "no problems" in page.locator("#hud").inner_text(), ev("rn.S.problems.map(p => p.message)"))
            check("the intro sequence plays on screen 1", ev("rn.S.seqs.running && rn.S.seqs.current.def.id") == "two_a_intro")
            page.wait_for_function("!rn.S.seqs.running", timeout=12000)
            # 1) take the apple while the guard is far away on the right
            page.wait_for_function("rn.S.guards[0].x > 1000", timeout=30000)
            tap(230, 455); page.wait_for_function("rn.G.inventory.includes('apple') || rn.S.over", timeout=20000); settle()
            check("Ren takes the apple (a distraction item)", ev("rn.G.inventory.includes('apple')"), guard())
            # 2) when he is walking away to the right, hide in the crate just past his left end
            page.wait_for_function("rn.S.guards[0].dir === 1 && rn.S.guards[0].x > 900", timeout=30000)
            tap(605, 430); page.wait_for_function("!!rn.S.ren.hidingIn || rn.S.over", timeout=20000)
            check("Ren hides in the crate", ev("rn.S.ren.hidingIn && rn.S.ren.hidingIn.id") == "crate", guard())
            page.screenshot(path=str(SHOTS / "e0_two_hidden.png"))
            # 3) he comes left to the end of his patrol (95 px from the hidden Ren), turns, and walks right again
            page.wait_for_function("rn.S.guards[0].x < 760 || rn.S.over", timeout=30000)
            page.wait_for_function("rn.S.guards[0].dir === 1 && rn.S.guards[0].x > 900 || rn.S.over", timeout=30000)
            check("the guard turns at the crate without seeing Ren", not ev("rn.S.over"), guard())
            # 4) follow behind him to the barrel on his path and hide again
            tap(1030, 430); page.wait_for_function("!!(rn.S.ren.hidingIn && rn.S.ren.hidingIn.id === 'barrel') || rn.S.over", timeout=20000)
            check("Ren follows behind him and hides in the barrel", not ev("rn.S.over"), guard())
            page.screenshot(path=str(SHOTS / "e1_two_barrel.png"))
            # 5) he walks back left past the barrel; then the apple keeps him busy on the left
            page.wait_for_function("rn.S.guards[0].dir === -1 && rn.S.guards[0].x < 900 || rn.S.over", timeout=30000)
            check("he walks past the barrel without catching Ren", not ev("rn.S.over"), guard())
            page.locator("#inv button", has_text="apple").click(); page.locator("#throw").click(); tap(640, 455)
            page.wait_for_function("rn.S.brains[0].state.mode === 'eating' || rn.S.over", timeout=15000)
            check("the thrown apple distracts him: he walks to it and eats", ev("rn.S.brains[0].state.mode") == "eating", guard())
            page.screenshot(path=str(SHOTS / "e1b_two_apple.png"))
            # 6) the key, then the gate
            reach(1520); tap(1520, 455); page.wait_for_function("rn.G.inventory.includes('key') || rn.S.over", timeout=20000); settle()
            check("Ren takes the key behind his back", ev("rn.G.inventory.includes('key')"), guard())
            reach(1700); page.locator("#inv button", has_text="key").click(); tap(1700, 420)
            page.wait_for_function("rn.G.states.gate !== 'locked' || rn.S.over", timeout=20000); settle()
            check("the key unlocks the gate and is used up", ev("rn.G.states.gate") == "closed" and not ev("rn.G.inventory.includes('key')"), page.locator("#msg").inner_text())
            tap(1700, 420); page.wait_for_function("rn.G.states.gate === 'open' || rn.S.over", timeout=20000); settle()
            check("the gate opens before he is back", ev("rn.G.states.gate") == "open" and not ev("rn.S.over"), guard())
            page.screenshot(path=str(SHOTS / "e2_two_gate_open.png"))
            # 7) through the door; screen 2's arrival sequence (not skipped)
            tap(1800, 420); page.wait_for_function("rn.S.name === 'two_b' && rn.S.seqs.running", timeout=20000)
            check("the door leads to screen 2 and its arrival sequence starts", True, ev("rn.S.seqs.current.def.id"))
            page.wait_for_function("rn.S.emotes.of('ren') === '?'", timeout=6000); page.screenshot(path=str(SHOTS / "e3_two_b_arrive.png"))
            page.wait_for_function("rn.S.cam.x > 300", timeout=8000)
            page.wait_for_function("rn.S.emotes.of('ren') === 'heart'", timeout=10000); page.screenshot(path=str(SHOTS / "e4_two_b_heart.png"))
            page.wait_for_function("!rn.S.seqs.running", timeout=8000)
            check("the arrival sequence shows ?, pans to the exit, then ! and a heart, and sets its flag",
                  ev("rn.S.emotes.log.join(' ')").endswith("ren:? ren:! ren:heart") and ev("rn.G.flags.reached_two_b") is True and "chime" in ev("rn.sounds.log"),
                  ev("rn.S.emotes.log.join(' ')"))
            # 6) progress survives a reload (on screen 2)
            page.goto(base_url); page.wait_for_selector("body[data-ready='1']")
            check("reload resumes on screen 2 with the gate open and the flag set", ev("rn.S.name") == "two_b" and ev("rn.G.states.gate") == "open" and ev("rn.G.flags.reached_two_b") is True,
                  f"{ev('rn.S.name')} {ev('JSON.stringify(rn.G.states)')}")
            # 7) out
            reach(1540); tap(1540, 420); page.wait_for_function("rn.S.won", timeout=25000)
            check("the exit on screen 2 ends the run", "got out" in page.locator("#msg").inner_text())
            page.screenshot(path=str(SHOTS / "e5_two_out.png"))
            # 8) getting caught: fresh start, walk straight at the guard
            page.locator("#reset").click(); page.wait_for_function("rn.S.name === 'two_a'", timeout=10000)
            ev("rn.S.seqs.skip()"); page.wait_for_timeout(200)
            page.wait_for_function("rn.S.guards[0].dir === -1", timeout=30000)
            tap(900, 455); page.wait_for_function("rn.S.over", timeout=30000)
            check("walking into his view ends in a catch", not ev("rn.S.won") and "caught" in page.locator("#msg").inner_text(), guard())
            page.screenshot(path=str(SHOTS / "e6_two_caught.png"))
            page.locator("#retry").click(); page.wait_for_timeout(300)
            check("retry restores the screen as it was entered", not ev("rn.S.over") and abs(ev("rn.S.ren.x") - 100) < 1 and ev("rn.G.states.gate") == "locked")
            check("no page errors", not errs, errs)
            br.close()
    finally:
        if srv: srv.terminate()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:2])))
