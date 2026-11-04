"""Serve the repo for the browser workbench and accept annotation saves.

    python workbench/serve.py            # http://localhost:8000/workbench/
    python workbench/serve.py --port 8123

Plain `python -m http.server` (run from the repo root) also works for viewing; then "Save" falls
back to downloading the JSON. This server additionally:
  PUT  /annotations/<character>/<action>.json   writes the annotation file (never inside assets/)
  POST /api/analyze?character=..&action=..       re-runs analyze.py so report.json uses the annotations
  POST /api/review {key, verdict, comment}       merges one verdict into annotations/_reviews.json
  POST /api/status                               background report preparation progress
  POST /api/inventory                            which out/ files and annotations exist, reviews, settings, pending
  POST /api/settings {character, game_scale, confirmed}   per-character scale in annotations/_settings.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402

NAME = r"[A-Za-z0-9_\-]+"
ANN_RE = re.compile(rf"^/annotations/({NAME})/({NAME})\.json$")


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # only log errors, not every GET
        if args and str(args[1])[:1] not in ("2", "3") and "favicon" not in str(args[0]) and "/annotations/" not in str(args[0]) and "/out/" not in str(args[0]):
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):
        m = ANN_RE.match(urlparse(self.path).path)
        if not m:
            return self._json(404, {"error": "only /annotations/<character>/<action>.json can be written"})
        try:
            doc = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if doc.get("format") != "workbench-action/1":
                raise ValueError("format must be workbench-action/1")
        except (ValueError, json.JSONDecodeError) as e:
            return self._json(400, {"error": str(e)})
        path = ROOT / "annotations" / m.group(1) / f"{m.group(2)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        return self._json(200, {"saved": str(path.relative_to(ROOT)).replace("\\", "/")})

    do_POST_paths = {"/api/analyze"}

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/api/analyze":
            q = parse_qs(u.query)
            try:
                rep = analyze.run(q["character"][0], q["action"][0])
            except Exception as e:  # report the failure to the page
                return self._json(500, {"error": repr(e)})
            return self._json(200, {"summary": rep["summary"]})
        if u.path == "/api/review":
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                key, verdict, comment = body["key"], body.get("verdict", ""), body.get("comment", "")
                if not re.fullmatch(rf"{NAME}/{NAME}", key) or verdict not in REVIEW_VERDICTS:
                    raise ValueError("bad key or verdict")
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                return self._json(400, {"error": str(e)})
            with REVIEW_LOCK:
                doc = load_reviews()
                doc["reviews"][key] = {"verdict": verdict, "comment": comment[:4000],
                                       "updated": datetime.now().isoformat(timespec="seconds")}
                REVIEWS.parent.mkdir(parents=True, exist_ok=True)
                REVIEWS.write_text(json.dumps(doc, indent=1), encoding="utf-8")
            return self._json(200, {"saved": key})
        if u.path in ("/api/identity", "/api/regions_check"):
            import regions
            q = parse_qs(u.query)
            c = q.get("character", [""])[0]
            if not re.fullmatch(NAME, c) or c not in analyze.load_manifest()["characters"]:
                return self._json(400, {"error": "unknown character"})
            try:
                if u.path == "/api/identity":
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                    seeds = {}
                    for name, r in body["regions"].items():
                        if not re.fullmatch(NAME, name):
                            raise ValueError(f"bad region name {name!r}")
                        x, y = (int(round(v)) for v in r["seed"])
                        seeds[name] = {"seed": [x, y]}
                    path = regions.save_seeds(c, seeds)
                    analyze._REGION_MODELS.pop(c, None)
                    return self._json(200, {"saved": analyze.rel(path), "regions": len(seeds)})
                a = q.get("action", [""])[0]
                model = regions.region_model(c)
                if not model:
                    raise ValueError("no seeds saved yet")
                act = analyze.load_action(c, a)
                per, summary, flags = regions.action_regions(act, model)
                img = analyze.OUT / c / f"regions_page_{a}.png"
                regions.compare_image(c, {a: (act, per, summary, flags)}, model, img)
                return self._json(200, {"summary": summary, "flags": flags, "image": "/" + analyze.rel(img),
                                        "bands": {n: m["band"] for n, m in model.items()}})
            except Exception as e:
                return self._json(400, {"error": repr(e)})
        if u.path == "/api/inventory":
            # one call instead of probing optional files (which 404 and fill the console)
            import settings
            inv = {}
            for c, ac in analyze.all_actions():
                od = analyze.OUT / c / ac
                inv[f"{c}/{ac}"] = {"out": sorted(f.name for f in od.iterdir()) if od.is_dir() else [],
                                    "annotation": (analyze.ANNOTATIONS / c / f"{ac}.json").exists(), "edited": edited(c, ac)}
            return self._json(200, {"actions": inv, "reviews": load_reviews(), "settings": settings.load(),
                                    "pending": STATUS["pending"], "running": STATUS["running"], "failed": STATUS["failed"]})
        if u.path == "/api/settings":
            import settings
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                c = body["character"]
                if c not in analyze.load_manifest()["characters"]:
                    raise ValueError("unknown character")
                v = float(body["game_scale"])
                if not 0.05 <= v <= 5:
                    raise ValueError("game_scale out of range (0.05-5)")
                settings.set_game_scale(c, v, bool(body.get("confirmed")))
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                return self._json(400, {"error": str(e)})
            threading.Thread(target=reexport, daemon=True).start()
            return self._json(200, {"saved": c, "game_scale": v})
        if u.path == "/api/status":
            return self._json(200, STATUS)
        if u.path == "/api/scene":
            import props
            try:
                doc = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                act = analyze.load_action(doc["character"], doc["action"], doc=doc)
                res = props.check_action(act, doc["scene"])
            except Exception as e:
                return self._json(400, {"error": repr(e)})
            return self._json(200, {"frames": [{k: f[k] for k in ("frame", "offset", "clip_px", "clip_at", "touching", "contacts")} for f in res["frames"]],
                                    "flags": res["flags"], "surfaces": props.surfaces(doc["scene"]), "solids": props.solids(doc["scene"])})
        if u.path == "/api/suggest-idle":
            import contextlib
            import io
            import edits
            q = parse_qs(u.query)
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    edits.main(["suggest-idle", q["character"][0], q["action"][0], "--write"])
            except SystemExit:
                return self._json(400, {"error": buf.getvalue().strip().splitlines()[-1]})
            return self._json(200, {"summary": buf.getvalue().splitlines()[0]})
        if ANN_RE.match(u.path):
            return self.do_PUT()
        return self._json(404, {"error": "unknown endpoint"})


REVIEWS = ROOT / "annotations" / "_reviews.json"
REVIEW_VERDICTS = {"", "approved", "needs work", "rejected", "unsure"}
REVIEW_LOCK = threading.Lock()
STATUS = {"pending": [], "done": [], "failed": {}, "running": False}


def load_reviews():
    if REVIEWS.exists():
        return json.loads(REVIEWS.read_text(encoding="utf-8"))
    return {"format": "workbench-reviews/1", "reviews": {}}


def edited(character, action):
    import edits
    doc = edits.load_doc(character, action)
    if not doc:
        return False
    fr = doc.get("frames", [])
    return bool(doc.get("mirror") or doc.get("snap_to_ground") or any(e.get("hold", 1) > 1 or e.get("drop") or e.get("offset") for e in fr))


def prepare_reports():
    """Background: analyse every action whose report is missing or older than its annotations / the analysis
    code (and before/after for edited ones),
    so the review page works on a fresh checkout with nothing but the server started."""
    import diagnostics
    STATUS["running"] = True
    code_t = max((HERE / f).stat().st_mtime for f in ("analyze.py", "edits.py", "regions.py", "diagnostics.py"))

    def stale(c, a):
        rep = analyze.OUT / c / a / "report.json"
        if not rep.exists():
            return True
        ann = [analyze.ANNOTATIONS / c / f"{a}.json", analyze.ANNOTATIONS / c / "_identity.json"]
        newest = max([code_t] + [f.stat().st_mtime for f in ann if f.exists()])
        return rep.stat().st_mtime < newest or (edited(c, a) and not (analyze.OUT / c / a / "before_after.png").exists())
    todo = [(c, a) for c, a in analyze.all_actions() if stale(c, a)]
    STATUS["pending"] = [f"{c}/{a}" for c, a in todo]
    for c, a in todo:
        try:
            if analyze.why_unusable(c, a) is None:
                if edited(c, a):
                    analyze.run(c, a, use_annotations=False, tag="original")
                analyze.run(c, a)
                if edited(c, a):
                    diagnostics.before_after(c, a, ("timing.png", "contact_sheet.png", "charts.png"))
            STATUS["done"].append(f"{c}/{a}")
        except Exception as e:  # keep going; the page shows what failed
            STATUS["failed"][f"{c}/{a}"] = repr(e)
        STATUS["pending"].remove(f"{c}/{a}")
    STATUS["running"] = False


def reexport():
    """After a settings change: rebuild the playtest exports so they use the new scale."""
    import contextlib
    import io
    import export
    with contextlib.redirect_stdout(io.StringIO()):
        export.main(["--demo"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-prepare", action="store_true", help="don't analyse missing reports in the background")
    a = p.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), partial(Handler, directory=str(ROOT)))
    if not a.no_prepare:
        threading.Thread(target=prepare_reports, daemon=True).start()
    print(f"Owner review: http://localhost:{a.port}/workbench/review.html")
    print(f"Workbench:    http://localhost:{a.port}/workbench/")
    srv.serve_forever()


if __name__ == "__main__":
    main()
