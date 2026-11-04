"""One climb, different ledge heights: pin the path to the planted contacts and check each height.

    python workbench/ledge_sweep.py ren climb_up                # 60-140% in 5% steps -> out/<c>/<a>/ledge_sweep.{json,png}
    python workbench/ledge_sweep.py ren climb_up --heights 80 100 120

For each height the ledge top moves (front edge fixed); the path is `from_contacts` (y from planted contacts on
their named surfaces, x holding shared contacts fixed). A height is "supported" when every planted contact is
within its tolerance (6 cell px feet, 14 hands) and no frame clips deeper than at the original height + 2 px.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze as A  # noqa: E402
import props as P  # noqa: E402


def scene_at(scene: dict, pct: float) -> dict:
    s = copy.deepcopy(scene)
    led = next(p for p in s["props"] if p["type"] == "ledge")
    h0 = s["floor_y"] - led["top_y"]
    led["top_y"] = s["floor_y"] - h0 * pct / 100
    base = s["path"] if s["path"]["type"] != "from_contacts" else s["path"]["base"]
    s["path"] = {"type": "from_contacts", "base": base}
    return s


def run(character, action, heights):
    act = A.load_action(character, action)
    scene = act.annotations["scene"]
    rows, results = [], {}
    for pct in heights:
        sc = scene_at(scene, pct)
        res = P.check_action(act, sc)
        worst = 0.0
        off, off_loose = [], []
        for f in res["frames"]:
            for c in f["contacts"]:
                if c["state"] == "planted" and c["dist"] is not None:
                    excess = c["dist"] - c.get("tol", P.TOL)
                    worst = max(worst, c["dist"])
                    if excess > 0:
                        off.append(f"{f['frame']}:{c['name']} {c['dist']:.0f}px")
                    if c["dist"] > 2 * c.get("tol", P.TOL):
                        off_loose.append(f"{f['frame']}:{c['name']} {c['dist']:.0f}px")
        clip = max(f["clip_depth"] for f in res["frames"])
        rows.append({"pct": pct, "height_px": round(scene["floor_y"] - next(p for p in sc["props"] if p["type"] == "ledge")["top_y"], 1),
                     "worst_contact_px": round(worst, 1), "contacts_off": off, "contacts_off_2x": off_loose, "max_clip_depth": clip,
                     "clip_frames": [f["frame"] for f in res["frames"] if f["clip_px"]]})
        results[pct] = res
    ref = next((r for r in rows if r["pct"] == 100), None)
    clip_ok = (ref["max_clip_depth"] if ref else 0) + 2
    for r in rows:
        r["supported"] = not r["contacts_off"] and r["max_clip_depth"] <= clip_ok
        r["supported_2x"] = not r["contacts_off_2x"] and r["max_clip_depth"] <= clip_ok + 8
    sup = [r["pct"] for r in rows if r["supported"]]
    sup2 = [r["pct"] for r in rows if r["supported_2x"]]
    summary = {"character": character, "action": action, "rule": f"all planted contacts within tolerance and clip depth <= {clip_ok:.0f}px (original + 2)",
               "supported_pct": [min(sup), max(sup)] if sup else None,
               "rule_2x": f"looser: contacts within 2x tolerance (12 px feet, 28 px hands) and clip depth <= {clip_ok + 8:.0f}px",
               "supported_pct_2x": [min(sup2), max(sup2)] if sup2 else None, "rows": rows,
               "note": "Outside the supported range these drawings do not work for that ledge: it needs new drawings or another climb category (step-up, pull-up)."}
    return act, summary, results


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("character"); p.add_argument("action")
    p.add_argument("--heights", type=float, nargs="*", default=sorted(set(range(60, 145, 5)) | set(range(85, 116))))
    p.add_argument("--images", type=float, nargs="*", default=[70, 90, 100, 110, 130], help="heights to draw scene images for")
    a = p.parse_args(argv)
    heights = sorted(set(a.heights) | set(a.images) | {100})
    act, summary, results = run(a.character, a.action, heights)
    od = A.output_dir(a.character, a.action)
    (od / "ledge_sweep.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    for r in summary["rows"]:
        print(f"{r['pct']:5.0f}% ({r['height_px']:.0f}px): {'SUPPORTED' if r['supported'] else ('2x-ok    ' if r['supported_2x'] else 'no       ')} worst contact {r['worst_contact_px']:.0f}px, "
              f"clip {r['max_clip_depth']:.0f}px{'; off: ' + ', '.join(r['contacts_off'][:6]) if r['contacts_off'] else ''}")
    print("supported range:", summary["supported_pct"], "% of the original height  (", summary["rule"], ")")
    print("looser range:   ", summary["supported_pct_2x"], "%  (", summary["rule_2x"], ")")
    for h in a.images:
        P.scene_image(act, results[h], title=f"{a.character}/{a.action} at {h:.0f}% ledge height ({summary['rows'][[r['pct'] for r in summary['rows']].index(h)]['height_px']:.0f} cell px), "
                      f"path pinned to contacts - {'SUPPORTED' if summary['rows'][[r['pct'] for r in summary['rows']].index(h)]['supported'] else 'NOT supported'}").save(od / f"ledge_{int(h)}.png", optimize=True)
    print("->", (od / "ledge_sweep.json").relative_to(A.ROOT))


if __name__ == "__main__":
    main()
