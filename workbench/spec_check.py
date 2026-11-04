"""Check a folder of new frames against a redraw spec.

    python workbench/spec_check.py specs/guard_walk.json path/to/new_frames
    python workbench/spec_check.py specs/ren_walk_inbetweens.json path/to/8_frames --travel 41.9
    python workbench/spec_check.py requests/guard_idle/spec.json path/to/idle_frames      # kind "idle" / "reaction" / "ladder"

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
                    game_scale=ch.get("game_scale_in_old_demos"), is_walk=spec.get("kind", "walk") == "walk",
                    reference=A.load_rgba(A.ASSETS / ref_rel) if ref_rel else None, reference_path=ref_rel)


def spec_travel(spec: dict) -> float:
    """Travel per frame a spec is checked at (walks); 0 for idles, reactions and ladders."""
    return float(spec.get("old_travel_px_per_frame") or spec.get("travel_px_per_frame") or 0.0)


def evaluate_still(spec: dict, act: A.Action, rep: dict) -> list[dict]:
    """Idles and reactions: drawings count, distinct poses, feet on the ground and still, breathing, identity flags."""
    c = spec["criteria"]
    ch, geo, feet = rep["metrics"]["change"], rep["metrics"]["geometry"], rep["metrics"]["feet"]
    flags = {f["code"] for f in rep["flags"]}
    out = []
    crit = lambda name, ok, got: out.append({"criterion": name, "meets": bool(ok), "measured": got})
    n = rep["frame_count"]; lo, hi = c["frame_count_range"]
    crit(f"{lo}-{hi} drawings", lo <= n <= hi, n)
    crit(f"at least {c['min_distinct']} distinct poses", ch["distinct_drawings"] >= c["min_distinct"], ch["distinct_drawings"])
    crit(f"at most {c['max_near_duplicates']} near-duplicate pairs (holds belong in the timing, not in repeated drawings)",
         len(ch["near_duplicates"]) <= c["max_near_duplicates"], len(ch["near_duplicates"]))
    if "max_pose_change_cv" in c:
        crit(f"even motion (pose change CV <= {c['max_pose_change_cv']})", ch["step_cv"] <= c["max_pose_change_cv"], round(ch["step_cv"], 2))
    bases = [g["baseline"] for g in geo]
    if c.get("grounded", True):
        crit(f"feet on ground y={spec['ground_y']} (+-{c['baseline_tolerance_px']}px) in every drawing",
             all(abs(b - spec["ground_y"]) <= c["baseline_tolerance_px"] for b in bases), [min(bases), max(bases)])
    if "feet_still_px" in c:   # the planted feet's outer edges barely move (an idle that slides or shuffles reads as restless)
        edges = [(min(cl["x0"] for cl in f["clusters"] if cl["planted"]), max(cl["x1"] for cl in f["clusters"] if cl["planted"]))
                 for f in feet if any(cl["planted"] for cl in f["clusters"])]
        drift = max(float(np.ptp([e[0] for e in edges])), float(np.ptp([e[1] for e in edges]))) if edges else None
        crit(f"planted feet still (edges move <= {c['feet_still_px']}px)", drift is not None and drift <= c["feet_still_px"], drift)
    if "breathing_pct" in c:   # visible but small rise and fall
        hs = [g["height"] for g in geo]; r = float(np.ptp(hs) / np.median(hs) * 100)
        crit(f"breathing: height varies {c['breathing_pct'][0]}-{c['breathing_pct'][1]}% of the figure", c["breathing_pct"][0] <= r <= c["breathing_pct"][1], round(r, 2))
    if "height_vs_reference" in c and act.reference is not None:
        ref_h = A.figure_geometry(act.reference)["height"]
        if ref_h:
            r = float(np.median([g["height"] for g in geo]) / ref_h)
            crit(f"same size as the reference (median height {c['height_vs_reference'][0]}-{c['height_vs_reference'][1]}x)", c["height_vs_reference"][0] <= r <= c["height_vs_reference"][1], round(r, 3))
    for code in c.get("no_flags", []):
        crit(f"no '{code}' flag", code not in flags, code in flags)
    return out


def evaluate_ladder(spec: dict, act: A.Action, rep: dict) -> list[dict]:
    """Ladder cycles: what can be measured without rung contacts. The rise per cycle needs contacts (workbench + ladder.py)."""
    c = spec["criteria"]
    ch, geo = rep["metrics"]["change"], rep["metrics"]["geometry"]
    out = []
    crit = lambda name, ok, got: out.append({"criterion": name, "meets": bool(ok), "measured": got})
    n = rep["frame_count"]
    crit(f"frame count = {c['frame_count']}", n == c["frame_count"], n)
    crit(f"distinct poses = {c['frame_count']}", ch["distinct_drawings"] == c["frame_count"], ch["distinct_drawings"])
    crit("no near-duplicate poses", not ch["near_duplicates"], len(ch["near_duplicates"]))
    lows = [g["baseline"] for g in geo]
    crit(f"the lowest foot changes height by >= {c['foot_height_range_min_px']}px over the cycle (proxy: lowest pixel)",
         float(np.ptp(lows)) >= c["foot_height_range_min_px"], float(np.ptp(lows)))
    out.append({"criterion": f"rise per cycle {c['rise_per_cycle_from_contacts']}+-{c['rise_tolerance_px']}px", "meets": None,
                "measured": "needs rung contacts: annotate them in the workbench, then python workbench/ladder.py"})
    return out


def evaluate(spec: dict, act: A.Action, rep: dict) -> list[dict]:
    kind = spec.get("kind", "walk")
    if kind in ("idle", "reaction"):
        return evaluate_still(spec, act, rep)
    if kind == "ladder":
        return evaluate_ladder(spec, act, rep)
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
    travel = a.travel or spec_travel(spec)
    act = load_folder(Path(a.folder), spec, travel)
    rep = A.analyze(act)
    res = evaluate(spec, act, rep)
    out = {"spec": a.spec, "folder": str(a.folder), "travel_px_per_frame": travel, "criteria": res,
           "meets_all_measurable": all(r["meets"] is not False for r in res), "manual_checks": spec["criteria"].get("manual", []),
           "summary": rep["summary"]}
    od = A.OUT / "spec_checks" / Path(a.folder).resolve().name
    od.mkdir(parents=True, exist_ok=True)
    (od / "spec_report.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    if not a.no_images:
        import diagnostics
        diagnostics.write_all(act, rep, od)
    for r in res:
        print(f"  {'meets ' if r['meets'] else 'MISSES' if r['meets'] is False else 'manual'}  {r['criterion']}: {r['measured']}")
    print(("All measurable criteria met" if out["meets_all_measurable"] else "Misses the spec") +
          " (not a judgement of how it looks). Still check by eye: " + "; ".join(out["manual_checks"]))
    print("->", A.rel(od / "spec_report.json"))
    return 0 if out["meets_all_measurable"] else 1


if __name__ == "__main__":
    sys.exit(main())
