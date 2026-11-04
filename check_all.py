"""One command for every check: pytest, every Node test, every Playwright check script, and the dist/ build + check.

    python check_all.py                 # everything, one after another (about 20-25 minutes)
    python check_all.py --only sandbox  # jobs whose name contains "sandbox"
    python check_all.py --skip-browser  # pytest + Node only
    python check_all.py --list          # show the jobs and exit

Prints a pass/fail table with the time of each job; full output of each job is in out/check_all/<job>.log and a summary
in out/check_all/summary.json. Exit code 0 only when nothing failed. Works on Windows and Linux (no shell syntax).
One-time setup: python -m pip install -r requirements.txt, then python -m playwright install chromium
(Node 18+ for the runtime tests: https://nodejs.org).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TESTS = ROOT / "workbench" / "tests"
LOGS = ROOT / "out" / "check_all"


def jobs() -> list[dict]:
    out = [{"name": "pytest", "group": "python", "cmd": [sys.executable, "-m", "pytest", "-q", str(TESTS)]}]
    for f in sorted((ROOT / "runtime" / "test").glob("*.test.mjs")):
        out.append({"name": f"node {f.stem.replace('.test', '')}", "group": "node", "cmd": ["node", "--test", str(f)]})
    for f in [TESTS / "screenshot_workbench.py", *sorted(TESTS.glob("*_checks.py"))]:
        if f.name == "robustness_checks.py":
            continue   # it is the dist job below
        out.append({"name": f.stem, "group": "browser", "cmd": [sys.executable, str(f)]})
    out.append({"name": "dist build + check", "group": "dist", "cmd": [sys.executable, str(TESTS / "robustness_checks.py")]})
    return out


def counts(group: str, text: str) -> str:
    if group == "python":
        m = re.search(r"(\d+) passed(?:, (\d+) failed)?", text)
        return f"{m.group(1)} passed" + (f", {m.group(2)} failed" if m and m.group(2) else "") if m else ""
    if group == "node":
        p, f = re.search(r"# pass (\d+)", text), re.search(r"# fail (\d+)", text)
        return f"{p.group(1) if p else '?'} passed, {f.group(1) if f else '?'} failed"
    p, f = len(re.findall(r"^PASS ", text, re.M)), len(re.findall(r"^FAIL ", text, re.M))
    return f"{p} passed, {f} failed" if p or f else ""


def preflight() -> dict:
    """Why a group can't run here (missing Node or browser), so it is reported as skipped rather than failed."""
    skip = {}
    if not shutil.which("node"):
        skip["node"] = "Node not found (install Node 18+ from nodejs.org)"
    try:
        sys.path.insert(0, str(TESTS))
        from playwright.sync_api import sync_playwright
        from screenshot_workbench import launch
        with sync_playwright() as p:
            launch(p).close()
    except Exception as e:   # no playwright package, or no browser installed
        why = f"Playwright/Chromium not usable ({type(e).__name__}): run  python -m playwright install chromium"
        skip["browser"] = skip["dist"] = why
    return skip


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", help="run jobs whose name contains this text")
    ap.add_argument("--skip-browser", action="store_true", help="skip the Playwright scripts and the dist check")
    ap.add_argument("--timeout", type=int, default=900, help="seconds per job (default 900)")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    todo = [j for j in jobs() if not a.only or a.only in j["name"]]
    if a.skip_browser:
        todo = [j for j in todo if j["group"] not in ("browser", "dist")]
    if a.list:
        for j in todo:
            print(f"{j['group']:8} {j['name']}")
        return 0
    LOGS.mkdir(parents=True, exist_ok=True)
    skip = preflight()
    rows, t_all = [], time.time()
    for j in todo:
        log = LOGS / (re.sub(r"[^\w.-]+", "_", j["name"]) + ".log")
        if j["group"] in skip:
            rows.append({**j, "result": "skipped", "detail": skip[j["group"]], "seconds": 0.0}); print(f"skip  {j['name']}: {skip[j['group']]}"); continue
        print(f"run   {j['name']} ...", flush=True)
        t0 = time.time()
        try:
            p = subprocess.run(j["cmd"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=a.timeout)
            text, code = p.stdout + p.stderr, p.returncode
        except subprocess.TimeoutExpired as e:
            text, code = f"{e.stdout or ''}{e.stderr or ''}\nTIMEOUT after {a.timeout} s", -1
        dt = time.time() - t0
        log.write_text(text, encoding="utf-8")
        fails = [l[5:120] for l in text.splitlines() if l.startswith("FAIL ")]
        detail = counts(j["group"], text) + (f"; first failure: {fails[0]}" if fails else "") + (" (timeout)" if code == -1 else "")
        rows.append({**j, "result": "pass" if code == 0 else "FAIL", "detail": detail, "seconds": round(dt, 1), "log": str(log.relative_to(ROOT))})
        print(f"      {'pass' if code == 0 else 'FAIL'} in {dt:.0f} s  {detail}")
    w = max(len(r["name"]) for r in rows) if rows else 10
    print("\n" + f"{'job'.ljust(w)}  result   time    detail")
    print("-" * (w + 60))
    for r in rows:
        print(f"{r['name'].ljust(w)}  {r['result'].ljust(7)}  {r['seconds']:6.1f}s  {r['detail']}")
    failed = [r for r in rows if r["result"] == "FAIL"]
    total = time.time() - t_all
    print("-" * (w + 60))
    print(f"{len(rows) - len(failed) - sum(r['result'] == 'skipped' for r in rows)} passed, {len(failed)} failed, "
          f"{sum(r['result'] == 'skipped' for r in rows)} skipped in {total / 60:.1f} min. Logs: {LOGS.relative_to(ROOT)}/")
    (LOGS / "summary.json").write_text(json.dumps({"rows": [{k: v for k, v in r.items() if k != "cmd"} for r in rows],
                                                   "failed": len(failed), "minutes": round(total / 60, 1)}, indent=1), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
