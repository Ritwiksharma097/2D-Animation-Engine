"""Review page lists an intake as 'new, awaiting owner' right after the action it would replace."""
import subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot_workbench import ROOT, SHOTS, free_port, launch  # noqa: E402


def main(key="guard/incoming__demo_synthetic", replaces="guard/walk"):
    port = free_port()
    srv = subprocess.Popen([sys.executable, str(ROOT / "workbench/serve.py"), "--port", str(port), "--no-prepare"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1); fails = 0
    try:
        with sync_playwright() as p:
            br = launch(p); page = br.new_page(viewport={"width": 1300, "height": 1000})
            bad = []; page.on("response", lambda r: bad.append(r.url) if r.status >= 400 else None)
            page.goto(f"http://127.0.0.1:{port}/workbench/review.html"); page.wait_for_selector("body[data-ready='1']", timeout=60000)
            titles = page.locator("section.card h2").all_inner_texts()
            i = next((k for k, t in enumerate(titles) if t.strip() == replaces), -1)
            new = titles[i + 1] if 0 <= i < len(titles) - 1 else ""
            ok = "NEW, awaiting owner" in new and key.split("__")[1] in new
            fails += not ok; print(("PASS" if ok else "FAIL"), "listed after", replaces, ":", new)
            card = page.locator("section.card.incoming", has_text=key.split("__")[1]).first
            card.scroll_into_view_if_needed(); page.wait_for_timeout(300)
            txt = card.inner_text()
            ok = "Spec" in txt and "would replace" in txt
            fails += not ok; print(("PASS" if ok else "FAIL"), "spec result and replacement shown")
            ok = not bad; fails += not ok; print(("PASS" if ok else "FAIL"), "no error responses", bad[:3])
            page.screenshot(path=str(SHOTS / "63_review_incoming.png"))
            br.close()
    finally:
        srv.terminate()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
