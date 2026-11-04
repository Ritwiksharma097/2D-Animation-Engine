"""Check a folder of new frames against a redraw spec.

    python workbench/spec_check.py specs/guard_walk.json path/to/new_frames
    python workbench/spec_check.py specs/ren_walk_inbetweens.json path/to/8_frames --travel 41.9

Frames are NN.png (sorted), transparent, the spec's cell size. Writes spec_report.json and the usual
diagnostic PNGs to out/spec_checks/<folder name>/ (never into the frames folder), and prints each criterion as "meets" or "MISSES".
"Meets" means the measurable criterion holds; it is not a judgement that the drawings look right.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze as A  # noqa: E402


def load_folder(folder: Path, spec: dict, travel: float) -> A.Action:
    files = sorted(Path(folder).glob("*.png"))
    if not files:
        raise SystemExit(f"no PNG frames in {folder}")
    man = A.load_manifest()
    ch = man["characters"][spec["character"]]
    ref_rel = ch.get("identity_reference")
    return A.Action(character=spec["character"], action=f"spec_check_{Path(folder).name}", files=files,
                    frames=[A.load_rgba(f) for f in files], durations_ms=[1000 / 12] * len(files), loop_mode="loop",
                    ground_y=float(spec["ground_y"]), travel=float(travel), travel_source="spec", travel_mode="constant",
                    game_scale=ch.get("game_scale_in_old_demos"), is_walk=True,
                    reference=A.load_rgba(A.ASSETS / ref_rel) if ref_rel else None, reference_path=ref_rel)


def evaluate(spec: dict, act: A.Action, rep: dict) -> list[dict]:
    c = spec["criteria"]
    ch, walk, geo = rep["metrics"]["change"], rep["metrics"]["walk"], rep["metrics"]["geometry"]
    flags = {f["code"] for f in rep["flags"]}
    out = []

    def crit(name, ok, got):
        out.append({"criterion": name, "meets": bool(ok), "measured": got})

    n = rep["frame_count"]
    crit(f"frame count = {c['frame_count']}", n == c["frame_count"], n)
    crit(f"distinct poses = {c['distinct_poses']}", ch["distinct_drawings"] == c["distinct_poses"], ch["distinct_drawings"])
    crit("no near-duplicate poses", len(ch["near_duplicates"]) == c["near_duplicates"], len(ch["near_duplicates"]))
    crit(f"steps per loop = {c['steps_per_loop']}", walk["steps_per_loop"] == c["steps_per_loop"], walk["steps_per_loop"])
    crit(f"clear passing pose (narrowest/widest stride <= {c['max_min_stride_ratio']})",
         walk["min_max_stride_ratio"] is not None and walk["min_max_stride_ratio"] <= c["max_min_stride_ratio"], round(walk["min_max_stride_ratio"] or 0, 2))
    crit(f"even motion (pose change CV <= {c['max_pose_change_cv']})", ch["step_cv"] <= c["max_pose_change_cv"], round(ch["step_cv"], 2))
    crit(f"slide at {act.travel:.1f} px/frame <= {c['max_slide_per_loop_px']} px per loop (heuristic lower bound)",
         walk["slide_total_px"] <= c["max_slide_per_loop_px"], round(walk["slide_total_px"], 1))
    bases = [g["baseline"] for g in geo]
    crit(f"feet on ground y={c['ground_y']} (+-{c['baseline_tolerance_px']}px)", all(abs(b - c["ground_y"]) <= c["baseline_tolerance_px"] for b in bases), [min(bases), max(bases)])
    for code in c["no_flags"]:
        crit(f"no '{code}' flag", code not in flags, code in flags)
    # planted foot targets: a planted heuristic cluster's sole must cover the target (+- tolerance)
    tol = c["planted_target_tolerance_px"]
    feet = rep["metrics"]["feet"]
    misses = []
    for k, fs in enumerate(spec["frames"][:n]):
        for name, t in fs["contacts"].items():
            if t["state"] != "planted":
                continue
            hit = any(cl["planted"] and cl["x0"] - tol <= t["x"] - fs.get("offset_x", 0) * 0 <= cl["x1"] + tol for cl in feet[k]["clusters"])
            if not hit:
                misses.append(f"{k + 1}:{name}@{t['x']:.0f}")
    crit(f"planted feet on their targets (+-{tol}px)", not misses, misses or "all on target")
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("spec"); p.add_argument("folder")
    p.add_argument("--travel", type=float, help="travel per frame (default: the spec's)")
    p.add_argument("--no-images", action="store_true")
    a = p.parse_args(argv)
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    travel = a.travel or spec.get("old_travel_px_per_frame") or spec["travel_px_per_frame"]
    act = load_folder(Path(a.folder), spec, travel)
    rep = A.analyze(act)
    res = evaluate(spec, act, rep)
    out = {"spec": a.spec, "folder": str(a.folder), "travel_px_per_frame": travel, "criteria": res,
           "meets_all_measurable": all(r["meets"] for r in res), "manual_checks": spec["criteria"].get("manual", []),
           "summary": rep["summary"]}
    od = A.OUT / "spec_checks" / Path(a.folder).resolve().name
    od.mkdir(parents=True, exist_ok=True)
    (od / "spec_report.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    if not a.no_images:
        import diagnostics
        diagnostics.write_all(act, rep, od)
    for r in res:
        print(f"  {'meets ' if r['meets'] else 'MISSES'}  {r['criterion']}: {r['measured']}")
    print(("All measurable criteria met" if out["meets_all_measurable"] else "Misses the spec") +
          " (not a judgement of how it looks). Still check by eye: " + "; ".join(out["manual_checks"]))
    print("->", A.rel(od / "spec_report.json"))
    return 0 if out["meets_all_measurable"] else 1


if __name__ == "__main__":
    sys.exit(main())
