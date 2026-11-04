"""Serve the repo for the browser workbench and accept annotation saves.

    python workbench/serve.py            # http://localhost:8000/workbench/
    python workbench/serve.py --port 8123

Plain `python -m http.server` (run from the repo root) also works for viewing; then "Save" falls
back to downloading the JSON. This server additionally:
  PUT  /annotations/<character>/<action>.json   writes the annotation file (never inside assets/)
  POST /api/analyze?character=..&action=..       re-runs analyze.py so report.json uses the annotations
"""
from __future__ import annotations

import argparse
import json
import re
import sys
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
        if ANN_RE.match(u.path):
            return self.do_PUT()
        return self._json(404, {"error": "unknown endpoint"})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), partial(Handler, directory=str(ROOT)))
    print(f"Workbench: http://localhost:{a.port}/workbench/")
    srv.serve_forever()


if __name__ == "__main__":
    main()
