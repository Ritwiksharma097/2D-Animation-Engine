"""Step 33: level editor v2 — placing hiding spots, doors, exits, objects, patrols and sequence triggers, the problem list
(unreachable things, patrols through solids, doors to missing screens, items no puzzle uses), and "play from here"
into the level runner with the unsaved draft."""
import json, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402


def main():
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port), "--no-prepare"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1); base = f"http://127.0.0.1:{port}"
    fails = 0
    def check(name, ok, detail=""):
        nonlocal fails; fails += not ok; print(("PASS " if ok else "FAIL ") + name + ": " + str(detail)[:200])
    saved = ROOT / "levels" / "_editor_v2_check.json"
    try:
        with sync_playwright() as p:
            br = launch(p); ctx = br.new_context(viewport={"width": 1500, "height": 900}); page = ctx.new_page(); errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            # the demo level: validation finds the key Ren can't reach (that platform is a deliberate refusal example)
            page.goto(f"{base}/workbench/level_editor.html?level=demo"); page.wait_for_selector("body[data-ready='1']")
            probs = page.evaluate("ed.problems.map(p => p.message)")
            check("demo: the problem list names the unreachable hotspot and why", any("hotspot item is unreachable" in m and "jump_max_gap" in m for m in probs), probs)
            page.screenshot(path=str(SHOTS / "d0_editor_demo_problems.png"))
            # scene_a: place one of everything and look at the problems
            page.goto(f"{base}/workbench/level_editor.html?level=scene_a"); page.wait_for_selector("body[data-ready='1']")
            check("scene_a starts with no problems", page.evaluate("ed.problems.length") == 0, page.evaluate("ed.problems.map(p => p.message)"))
            box = page.locator("#cv").bounding_box(); k = box["width"] / page.evaluate("ed.level.size[0]")
            click = lambda x, y: page.mouse.click(box["x"] + x * k, box["y"] + y * k)
            add = (lambda kind, x, y=460: (click(x, y), page.locator(f"[data-add='{kind}']").click()))
            add("ledge", 640)
            add("patrol", 600)
            add("door", 300); add("hotspot", 200); add("hiding", 420); add("exit", 1760); add("trigger", 1200)
            page.locator("#objkind").select_option("chest"); add("object", 860)
            P = page.evaluate("ed.problems.map(p => p.message)")
            has = lambda s: any(s in m for m in P)
            check("a patrol across the new ledge is reported", has("runs through ledge"), [m for m in P if "patrol" in m])
            check("a door to a screen that doesn't exist is reported", has('leads to missing screen "other_screen"') and has("no such level file"), [m for m in P if "door" in m])
            check("an item no puzzle uses is reported", has('item "item" is never used'), [m for m in P if "item" in m])
            kinds = page.evaluate("[...new Set(ed.items().map(i => i.kind))].sort()")
            check("every new kind is placed and drawn", all(x in kinds for x in ["hiding", "door", "exit", "object", "patrol", "trigger", "ledge", "hotspot"]), kinds)
            page.screenshot(path=str(SHOTS / "d1_editor_v2_problems.png"))
            # an unreachable hotspot: put one on a platform nobody can get to
            page.evaluate("ed.level.platforms = [{id: 'high', x0: 1500, x1: 1650, top: 200}]; ed.level.hotspots.push({id: 'star', x: 1550, on: 'high', item: 'star'}); ed.refresh()")
            check("a hotspot on an unreachable platform is reported", any("hotspot star is unreachable" in m for m in page.evaluate("ed.problems.map(p => p.message)")))
            # clicking a problem selects the thing it is about
            page.locator(".prob", has_text="runs through ledge").first.click()
            check("clicking a problem selects its item", "patrol" in page.locator("#props").inner_text(), page.locator("#props").inner_text()[:60])
            # edit a property in the panel: move the patrol back off the ledge
            page.evaluate("(() => { const p = ed.level.patrols.find(p => p.id === 'guard1'); p.x0 = 820; p.x1 = 1000; p.start_x = 900; ed.refresh(); })()")
            check("fixing the patrol clears its problem", not any("runs through" in m for m in page.evaluate("ed.problems.map(p => p.message)")))
            # play from here, with the unsaved draft
            click(250, 460)
            page.locator("#name").fill("_editor_v2_check")
            with ctx.expect_page() as info:
                page.locator("#play").click()
            run = info.value; run.on("pageerror", lambda e: errs.append("runner: " + str(e)))
            run.wait_for_selector("body[data-ready='1']", timeout=20000)
            rx = run.evaluate("rn.S.ren.x"); title = run.locator("#title").inner_text()
            check("play from here opens the runner at the clicked spot with the draft", abs(rx - 250) < 2 and "editor draft" in title, f"x {rx} | {title}")
            check("the runner has the new chest and hiding spot", run.evaluate("rn.S.objects.some(o => o.kind === 'chest') && rn.S.scene.hiding.length === 2"))
            run.wait_for_timeout(500); run.evaluate("rn.S.seqs.skip()"); run.wait_for_timeout(300)
            run.screenshot(path=str(SHOTS / "d2_runner_from_editor.png"))
            check("the runner lists the same level problems", "LEVEL PROBLEMS" in run.locator("#hud").inner_text())
            # save, reload
            page.locator("#save").click(); page.wait_for_timeout(500)
            check("save writes every new key", saved.exists() and all(key in json.loads(saved.read_text()) for key in ["hiding_spots", "doors", "objects", "patrols", "sequences"]), page.locator("#msg").inner_text())
            check("no page errors", not errs, errs)
            br.close()
    finally:
        srv.terminate()
        if saved.exists(): saved.unlink()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
