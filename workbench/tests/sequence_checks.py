"""Step 31: sequences (level start, hotspot, after a door), skipping, emote bubbles (sequence- and AI-driven), sound hooks
and the mute toggle, in sandbox/scenes.html."""
import subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402


def main(base_url=None):
    port = free_port(); srv = None
    if not base_url:
        srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port), "--no-prepare"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1); base_url = f"http://127.0.0.1:{port}/sandbox/scenes.html"
    fails = 0
    def check(name, ok, detail=""):
        nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + str(detail)[:170])
    try:
        with sync_playwright() as p:
            br = launch(p); page = br.new_page(viewport={"width": 1240, "height": 860}); errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(base_url); page.wait_for_selector("body[data-ready='1']")
            box = page.locator("#cv").bounding_box(); k = box["width"] / 1200; ev = page.evaluate
            def tap(wx, wy):
                cam = ev("sd.S.cam.x"); page.mouse.click(box["x"] + (wx - cam) * k, box["y"] + wy * k)
            # level start intro: runs, blocks input, pans the camera to the guard, shows emotes
            check("the level_start sequence runs on load", ev("sd.seqs.running && sd.seqs.current.def.id") == "intro_a")
            check("the skip button is shown while it runs", page.locator("#skip").is_visible())
            page.wait_for_timeout(300); page.screenshot(path=str(SHOTS / "b0_seq_emote_ren.png"))
            check("an emote bubble is up over Ren", ev("sd.S.emotes.of('ren')") == "...")
            x0 = ev("sd.S.ren.x"); tap(500, 460); page.wait_for_timeout(600)
            check("player input is ignored during a sequence", ev("sd.S.ren.x") == x0)
            page.wait_for_function("sd.S.cam.x > 500", timeout=5000)
            page.wait_for_function("sd.S.emotes.of('guard') === 'zZz'", timeout=5000)
            page.screenshot(path=str(SHOTS / "b1_seq_pan_guard.png"))
            check("the camera pans to the guard, who shows zZz", True, f"cam {ev('sd.S.cam.x'):.0f}")
            page.wait_for_function("!sd.seqs.running", timeout=8000)
            check("the intro ends, the skip button hides, input is back", not page.locator("#skip").is_visible())
            # hotspot sequence: the sign post
            ev("(() => { const g = sd.S.guard; g.clear(); g.next(); g.x = 1450; g.dir = 1; sd.S.brain.cfg.patrol = [1450, 1450]; })()")
            page.wait_for_function("sd.S.cam.x < 60", timeout=8000)
            tap(330, 440); page.wait_for_function("sd.seqs.running && sd.seqs.current.def.id === 'read_sign'", timeout=15000)
            page.wait_for_function("sd.S.emotes.of('ren') === 'heart'", timeout=6000)
            page.screenshot(path=str(SHOTS / "b2_seq_sign_heart.png"))
            page.wait_for_function("!sd.seqs.running", timeout=6000)
            check("clicking the sign plays its sequence: Ren faces it, ?, heart, flag set", ev("sd.FLAGS.read_sign") is True and ev("sd.S.emotes.log.join(' ')").endswith("ren:? ren:heart"),
                  ev("sd.S.emotes.log.join(' ')"))
            check("sound hooks fired (steps while walking, the chime)", "step" in ev("sd.sounds.log") and "chime" in ev("sd.sounds.log"), ev("sd.sounds.log.slice(-6).join(' ')"))
            check("audio unlocked on the first click", ev("!!sd.sounds.ac"))
            # AI-driven emote: suspicion makes the guard show '?'
            ev("(() => { const g = sd.S.guard; g.x = 700; g.dir = -1; sd.S.brain.cfg.patrol = [700, 700]; sd.S.ren.x = 480; })()")
            page.wait_for_function("sd.S.emotes.of('guard') === '?'", timeout=6000)
            page.screenshot(path=str(SHOTS / "b3_seq_guard_question.png"))
            check("the guard's suspicious mode shows a ? bubble", True, ev("sd.S.brain.state.mode"))
            # door -> screen B: its arrival sequence starts after the fade; Escape skips it to the end state
            page.wait_for_function("sd.S.over", timeout=8000)
            ev("document.getElementById('retry').click()")
            ev("(() => { sd.S.guard.x = 1800; sd.S.brain.cfg.patrol = [1790, 1790]; sd.S.ren.x = 1600; })()")
            page.wait_for_function("sd.S.cam.x > 560", timeout=8000)
            tap(1730, 420); page.wait_for_function("sd.S.name === 'scene_b' && sd.seqs.running", timeout=15000)
            check("screen B's arrival sequence starts after the fade", ev("sd.fader.busy") is False, ev("sd.seqs.current.def.id"))
            page.keyboard.press("Escape"); page.wait_for_timeout(100)
            check("Escape skips it: Ren at its end point, flag set, camera free", not ev("sd.seqs.running") and abs(ev("sd.S.ren.x") - 260) < 1 and ev("sd.FLAGS.saw_exit") is True,
                  f"x {ev('sd.S.ren.x'):.0f} flags {ev('JSON.stringify(sd.FLAGS)')}")
            # mute persists
            page.locator("#mute").check(); n = ev("sd.sounds.log.length"); ev("sd.sounds.play('chime')")
            check("mute: sounds still logged but muted", ev("sd.sounds.muted") and ev("sd.sounds.log.length") == n + 1)
            page.reload(); page.wait_for_selector("body[data-ready='1']")
            check("mute is remembered after a reload", ev("sd.sounds.muted") and page.locator("#mute").is_checked())
            page.locator("#mute").uncheck()
            check("no page errors", not errs, errs)
            br.close()
    finally:
        if srv: srv.terminate()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:2])))
