"""Exercise workbench interactions in Chromium and assert their effects; screenshots go to out/screenshots/.

    python workbench/tests/ui_checks.py

Checks: drag a contact, shift-click delete, ping-pong order, per-frame durations driving playback.
Nothing is saved, so annotations/ is not changed.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402
sys.path.insert(0, str(HERE.parent))

results: list[tuple[str, bool, str]] = []


def check(name, ok, detail):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + ": " + detail)


def canvas_point(page, cell_x, cell_y):
    box = page.locator("section.viewer").first.locator("canvas.view").bounding_box()
    cell_w = page.evaluate("workbench.viewers[0].cell[0]")
    k = box["width"] / cell_w
    return box["x"] + cell_x * k, box["y"] + cell_y * k


def open_page(page, base, h):
    page.goto("about:blank")
    page.goto(base + h)
    page.wait_for_selector("body[data-ready='1']", timeout=15000)


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "workbench" / "serve.py"), "--port", str(port)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    base = f"http://127.0.0.1:{port}/workbench/index.html"
    try:
        with sync_playwright() as p:
            br = launch(p)
            page = br.new_page(viewport={"width": 1500, "height": 1250})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            # ---- drag a contact (annotated keypose, frame 1, heel_l at x=403)
            open_page(page, base, "#a=ren/walk_keypose&zoom=1&frame=1")
            c0 = page.evaluate("workbench.viewers[0].frames[0].contacts.heel_l")
            x, y = canvas_point(page, c0["x"], c0["y"])
            page.mouse.move(x, y); page.mouse.down()
            for k in range(1, 6):
                page.mouse.move(x + 6 * k, y - 4 * k)
            page.mouse.up()
            c1 = page.evaluate("workbench.viewers[0].frames[0].contacts.heel_l")
            check("drag moves contact", abs(c1["x"] - (c0["x"] + 30)) < 2 and abs(c1["y"] - (c0["y"] - 20)) < 2,
                  f"heel_l {c0['x']:.0f},{c0['y']:.0f} -> {c1['x']:.0f},{c1['y']:.0f} (expected +30,-20)")
            n_names = page.evaluate("Object.keys(workbench.viewers[0].frames[0].contacts).length")
            check("drag does not add a point", n_names == 2, f"{n_names} contacts on frame 1")
            page.screenshot(path=str(SHOTS / "10_drag_contact.png"), full_page=True)

            # ---- shift-click delete toe_r
            t = page.evaluate("workbench.viewers[0].frames[0].contacts.toe_r")
            x, y = canvas_point(page, t["x"] + 3, t["y"] - 2)
            page.keyboard.down("Shift"); page.mouse.click(x, y); page.keyboard.up("Shift")
            names = page.evaluate("Object.keys(workbench.viewers[0].frames[0].contacts)")
            check("shift-click deletes nearest", names == ["heel_l"], f"contacts now {names}")
            rows = page.locator("section.viewer").first.locator("table.contacts tr").count()
            check("contact table updates", rows == 1, f"{rows} row(s) in table")
            page.screenshot(path=str(SHOTS / "11_shift_click_delete.png"), full_page=True)
            # reload without saving: file on disk unchanged
            open_page(page, base, "#a=ren/walk_keypose&zoom=1")
            n = page.evaluate("Object.keys(workbench.viewers[0].frames[0].contacts).length")
            check("unsaved edits are not written", n == 2, f"{n} contacts after reload")

            # ---- ping-pong: step with the next button and record the order
            open_page(page, base, "#a=guard/idle&a.raw=1&zoom=0.5")  # raw: 14 frames, no holds/drops
            v = page.locator("section.viewer").first
            v.locator(".loop-mode").select_option("pingpong")
            order = [page.evaluate("workbench.viewers[0].idx")]
            for _ in range(30):
                v.locator(".b-next").click()
                order.append(page.evaluate("workbench.viewers[0].idx"))
            expected = (list(range(14)) + list(range(12, 0, -1))) * 2
            check("ping-pong order", order == expected[:31], "frames " + ",".join(str(i + 1) for i in order))
            # and while playing
            played = page.evaluate("""async () => { const v = workbench.viewers[0]; v.jump(0); v.setPlaying(true);
                const seen = []; const t0 = performance.now();
                while (performance.now() - t0 < 2600) { const i = v.idx; if (seen[seen.length-1] !== i) seen.push(i); await new Promise(r => setTimeout(r, 10)); }
                v.setPlaying(false); return seen; }""")
            check("ping-pong while playing", played[:27] == expected[:27], "played " + ",".join(str(i + 1) for i in played[:30]))

            # ---- per-frame durations: frame 1 = 1000 ms via its timeline input, the rest 83 ms
            open_page(page, base, "#a=ren/walk_keypose&zoom=0.5")
            v = page.locator("section.viewer").first
            inp = v.locator(".tl input").nth(0)
            inp.fill("1000"); inp.press("Enter"); inp.dispatch_event("change")
            v.locator(".tl input").nth(2).fill("400"); v.locator(".tl input").nth(2).dispatch_event("change")
            durs = page.evaluate("workbench.viewers[0].frames.map(f => f.duration_ms)")
            timing = page.evaluate("""async () => { const v = workbench.viewers[0]; v.jump(0); v.setPlaying(true);
                const log = []; let last = v.idx, t = performance.now(); const t0 = t;
                while (performance.now() - t0 < 3300) { await new Promise(r => requestAnimationFrame(r));
                  if (v.idx !== last) { const now = performance.now(); log.push([last, Math.round(now - t)]); last = v.idx; t = now; } }
                v.setPlaying(false); return log; }""")
            held = {}
            for i, ms in timing[:-1]:
                held.setdefault(i, []).append(ms)
            mean = {i + 1: round(sum(m) / len(m)) for i, m in held.items()}
            ok = abs(mean.get(1, 0) - 1000) < 60 and abs(mean.get(3, 0) - 400) < 40 and abs(mean.get(2, 0) - 83) < 30
            check("durations drive playback", ok, f"set {durs} ms; measured mean hold per frame {mean}")
            page.screenshot(path=str(SHOTS / "12_durations.png"), full_page=True)
            # ---- edit layer: guard idle holds/drops from annotations/guard/idle.json
            open_page(page, base, "#a=guard/idle&b=guard/idle&b.raw=1&zoom=0.5")
            seq = page.evaluate("workbench.viewers[0].seq")
            doc = __import__("json").loads((ROOT / "annotations/guard/idle.json").read_text())
            kept = [i for i, e in enumerate(doc["frames"]) if not e.get("drop")]
            check("dropped entries leave playback", seq == kept, f"seq {seq} vs kept entries {kept}")
            durs = page.evaluate("workbench.viewers[0].seq.map(i => workbench.viewers[0].dur(i))")
            want = [e["duration_ms"] * e.get("hold", 1) for e in doc["frames"] if not e.get("drop")]
            check("hold x duration used for playback", all(abs(a - b) < 0.5 for a, b in zip(durs, want)), f"{[round(d) for d in durs]} ms")
            raw = page.evaluate("[workbench.viewers[1].seq.length, workbench.viewers[1].ann]")
            check("raw viewer ignores edits", raw[0] == 14 and raw[1] is None, f"raw viewer plays {raw[0]} frames")
            import edits as _ed, analyze as _an
            low = _ed.lowest_pixel(_an.load_rgba(ROOT / "assets/guard/idle/01.png"))
            snap = page.evaluate("workbench.viewers[0].xf(0).dy")
            check("snap moves floating idle to ground", snap == 535 - low, f"frame 1 dy {snap} (lowest pixel {low} -> 535)")
            page.screenshot(path=str(SHOTS / "14_idle_edits_vs_original.png"), full_page=True)

            # ---- mirror: contact display + drag mapping stay consistent
            open_page(page, base, "#a=ren/walk_keypose&zoom=1&frame=1")
            v = page.locator("section.viewer").first
            v.locator(".e-mirror").check()
            view = page.evaluate("workbench.viewers[0].contactsOf(0).find(c => c.name === 'heel_l')")
            check("mirror flips contact display", abs(view["x"] - (639 - 403)) < 0.6, f"heel_l shown at x={view['x']:.1f} (639-403=236)")
            x, y = canvas_point(page, view["x"], view["y"])
            page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x + 20, y); page.mouse.up()
            src = page.evaluate("workbench.viewers[0].frames[0].contacts.heel_l.x")
            check("drag on mirrored frame edits source coords", abs(src - (403 - 20)) < 1.5, f"source x {src:.1f} (expected 383)")
            page.screenshot(path=str(SHOTS / "15_mirror.png"), full_page=True)
            t = page.evaluate("[workbench.viewers[0].sign, workbench.viewers[0].contactTravel(0, 1).value]")
            check("mirrored travel still positive along facing", t[0] == -1 and t[1] > 0, f"sign {t[0]}, travel {t[1]:.1f}")

            check("no page errors", not errors, "; ".join(errors) or "none")
            br.close()
    finally:
        srv.terminate()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
