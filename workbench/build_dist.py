"""Copy the runtime, the game exports, the demo levels and the sandbox into one static folder (default `dist/`).

The result needs no server code: any static host (python -m http.server, nginx, GitHub Pages, itch.io html upload)
serves it. Relative paths are kept as in the repo (sandbox/ loads ../runtime/ and ../out/export/), so the pages work
unchanged. Nothing in assets/ or annotations/ is copied: the exports already carry what the runtime needs.

    python workbench/build_dist.py [--out dist]
"""
import argparse, json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS = [  # (source, destination relative to the dist folder, glob patterns)
    ("runtime", "runtime", ["*.js", "README.md"]),
    ("out/export", "out/export", ["**/*.json", "**/*.png", "*.html"]),
    ("levels", "levels", ["*.json"]),
    ("sandbox", "sandbox", ["*.html", "*.json"]),
]
INDEX = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Animation runtime demos</title>
<style>body{font:15px/1.5 system-ui,sans-serif;margin:24px;max-width:720px;color:#1e1e1e}li{margin:6px 0}code{background:#eee;padding:0 3px}</style>
</head><body>
<h1>Animation runtime demos</h1>
<p>Static build made by <code>workbench/build_dist.py</code>. Placeholder shapes and existing art only; not the game.</p>
<ul>
<li><a href="sandbox/index.html">Mechanics sandbox</a>: reach the key past the guard</li>
<li><a href="sandbox/scenes.html">Scene demo</a>: layers, hiding spot, doors</li>
<li><a href="sandbox/puzzle.html">Puzzle room</a>: objects, item use, save</li>
<li><a href="out/export/play.html">Ren playtest</a>: walk, climb, jump, ledge-height control</li>
<li><a href="out/export/guard_demo.html">Guard demo</a>: patrol, food, ladder</li>
<li><a href="out/export/level_play.html">Level demo</a>: pathfinding and camera</li>
</ul>
<p>Built from {n} files.</p>
</body></html>
"""


def build(out: Path) -> list[Path]:
    out = out.resolve()
    if out == ROOT or out in ROOT.parents or any(out == ROOT / d or (ROOT / d) in out.parents for d in ("assets", "annotations", "runtime", "sandbox", "out", "levels", "workbench")):
        raise SystemExit(f"refusing to build into {out}")
    if out.exists():
        shutil.rmtree(out)
    files = []
    for src, dst, patterns in PARTS:
        base = ROOT / src
        if not base.exists():
            raise SystemExit(f"missing {base}: run the export step first (see README)")
        for pat in patterns:
            for f in sorted(base.glob(pat)):
                if f.is_file() and "test" not in f.relative_to(base).parts:
                    t = out / dst / f.relative_to(base)
                    t.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, t)
                    files.append(t)
    tuning = json.loads((out / "sandbox/tuning.json").read_text(encoding="utf-8"))
    if not (out / "sandbox" / tuning["exports"]).resolve().is_dir():
        raise SystemExit(f"sandbox tuning.json exports path {tuning['exports']!r} does not resolve inside {out}")
    (out / "index.html").write_text(INDEX.replace("{n}", str(len(files))), encoding="utf-8")
    return files


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    a = ap.parse_args()
    files = build(a.out)
    size = sum(f.stat().st_size for f in files)
    print(f"wrote {len(files)} files ({size / 1e6:.1f} MB) to {a.out}; serve with: python -m http.server -d {a.out}")
