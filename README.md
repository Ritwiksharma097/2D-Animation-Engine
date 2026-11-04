# 2D animation workbench

Diagnoses sprite animation problems (sliding feet, repeated or uneven frames, identity drift) so they
can be found from still images and numbers instead of by watching playback. See `CLAUDE.md` for the
brief, `FORMAT.md` for the data formats, `PROGRESS.md` for status and `REPORT.md` for results.

## Setup (Windows or Linux, Python 3.13/3.14)

```
python -m venv .venv
.venv\Scripts\activate        (Windows)   |   source .venv/bin/activate   (Linux/macOS)
pip install -r requirements.txt
```

## Analyse an action

```
python workbench/analyze.py guard walk
python workbench/analyze.py ren walk_keypose --travel 41.9
python workbench/analyze.py --all
```

Arguments are a character and action name from `assets/manifest.json`. `--travel` is the travel per
frame in cell pixels (otherwise taken from the annotation file or the manifest's `old_timing`).
`--no-annotations` ignores `annotations/` and uses the heuristics. `--no-images` skips PNGs.

Output goes to `out/<character>/<action>/report.json` (plus diagnostic PNGs). `summary` is plain
English; `flags` are only ever "suspect"; `limits` says what each heuristic cannot tell.

## Tests

```
python -m pytest workbench/tests
```
