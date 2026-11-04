"""Art request packs for the next art round: one folder per action under requests/ (not art; what to draw and how it is checked).

    python workbench/art_requests.py            # writes requests/<id>/ for every request, and requests/README.md

Each pack: README.md (what, why, rank, what is wrong now, checklist, the intake command), identity/ (reference figure,
labelled region crops, the character's approved poses at one scale), the spec sheet if there is one, spec.json (criteria
spec_check.py measures), prompt.txt (an image-generation template), current.png (the drawings being replaced).
Nothing in assets/ is written.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze as A  # noqa: E402
import regions as R  # noqa: E402

REQ = A.ROOT / "requests"

# Ranked by how much each blocks the sandbox (sandbox/run.html?level=two_a). Higher = seen more, or more wrong, there.
REQUESTS = [
    {"id": "guard_walk", "character": "guard", "replaces": "walk", "new_action": "walk_v2", "spec": "specs/guard_walk.json", "sheet": "specs/guard_walk.png",
     "blocks": "He patrols on every screen. His walk is rejected, walks in place, and at the placeholder speed (annotations/_settings.json) his feet slide; the HUD shows it in red.",
     "what": "A new 8-drawing patrol walk: contact, down, passing, up, then the same with the legs swapped.",
     "poses": None},
    {"id": "guard_idle", "character": "guard", "replaces": "idle", "new_action": "idle_v2", "spec": None, "sheet": None,
     "blocks": "Plays at both ends of every patrol (1.5 s each) and while he is suspicious. Rejected: much too fast, about 4-5 distinct drawings repeated.",
     "what": "A calm, grumpy breathing idle in 6 drawings (the timing comes from the edit layer, so no repeated drawings are needed).",
     "poses": ["1 neutral stance, weight even, scowl", "2 inhale: chest and shoulders up ~1-2% of his height, moustache unchanged", "3 top of the breath (held in the timing)",
               "4 exhale: shoulders settle", "5 settle slightly lower than 1, a small grumpy head tilt or eye narrowing", "6 back toward 1 (the loop seam)"],
     "criteria": {"frame_count_range": [6, 8], "min_distinct": 5, "max_near_duplicates": 1, "grounded": True, "baseline_tolerance_px": 3, "feet_still_px": 4,
                  "breathing_pct": [0.4, 3.0], "no_flags": ["out_of_order"],
                  "manual": ["he stays grumpy and recognisably the same guard as his approved happy / interact / eating actions",
                             "the motion reads as breathing, not as a jitter; feet do not move at all"]}},
    {"id": "ren_walk_inbetweens", "character": "ren", "replaces": "walk_keypose", "new_action": "walk_8", "spec": "specs/ren_walk_inbetweens.json", "sheet": "specs/ren_walk_inbetweens.png",
     "blocks": "Ren's walk is approved but has 4 drawings, so every walk in the sandbox looks choppy whatever the travel. It is the most-seen animation.",
     "what": "The 4 in-betweens the owner asked for, between the 4 approved key poses (8 frames: key, in-between, key, ...). Keep the keys' look exactly.",
     "poses": None},
    {"id": "ren_reactions", "character": "ren", "replaces": "caught_game_over", "new_action": "caught_game_over_v2", "spec": None, "sheet": None,
     "also": ["happy", "hurt_stumble"],
     "blocks": "caught_game_over plays on every catch; its sleeves and tunic are recoloured (REPORT.md, Phase 5). happy (bigger, rounder head) and hurt_stumble (recoloured face and sleeves) are not used by the sandbox yet but will be by any story beat.",
     "what": "Redraw or recolour Ren's drifting reactions so colours and proportions match his idle and walk: caught_game_over first, then happy and hurt_stumble.",
     "poses": ["caught_game_over: surprise, then sits down; same colours as the idle", "happy: same head size as the walk (the current one is more chibi)", "hurt_stumble: loses balance and recovers; face and sleeve colours as the idle"],
     "criteria": {"frame_count_range": [8, 14], "min_distinct": 8, "max_near_duplicates": 2, "grounded": False, "baseline_tolerance_px": 3,
                  "no_flags": ["region_colour_drift", "region_size_drift"],
                  "manual": ["same face, hood shape and proportions as ren/idle (the region check sees colour and size, not shape)",
                             "pose changes read clearly at game size (about 200 px tall)"]}},
    {"id": "ren_idle", "character": "ren", "replaces": "idle", "new_action": "idle_v2", "spec": None, "sheet": None,
     "blocks": "Ren stands still between clicks; the approved idle is one still drawing (it 'does nothing'). Not wrong, just lifeless.",
     "what": "An idle that does something: breathing plus a blink and a small glance or satchel-strap adjust, 8 drawings, feet planted.",
     "poses": ["1 the approved idle pose", "2 inhale", "3 top of the breath, eyes start to close", "4 blink (eyes closed)", "5 eyes open, glance toward the viewer",
               "6 hand adjusts the satchel strap", "7 exhale, hand back", "8 back toward 1"],
     "criteria": {"frame_count_range": [6, 10], "min_distinct": 6, "max_near_duplicates": 1, "grounded": True, "baseline_tolerance_px": 3, "feet_still_px": 4,
                  "breathing_pct": [0.4, 3.0], "height_vs_reference": [0.97, 1.03], "no_flags": ["region_colour_drift", "region_size_drift", "out_of_order"],
                  "manual": ["frame 1 is the approved idle drawing (identity reference) or indistinguishable from it",
                             "the glance can be the 'looks at the player' hint the game wants"]}},
    {"id": "guard_ladder", "character": "guard", "replaces": "ladder_up", "new_action": "ladder_up_v2", "spec": "specs/guard_ladder.json", "sheet": "specs/guard_ladder.png",
     "blocks": "Not used by the sandbox (the guard AI never climbs). Rejected; the current cycle keeps his feet at one height, so it cannot land on rungs.",
     "what": "An 8-drawing back-view ladder cycle that climbs two rungs: diagonal hand and foot move together, then swap.",
     "poses": None},
]

PROMPT_NOTE = ("NOTE: the brief points to the old sprite_rework README's prompt section, 'summarised in the handoff'. That text is not in "
               "this repository: assets/reference/GPT_HANDOFF.md summarises what went wrong, not the prompt wording. This template is built "
               "from the handoff's lessons and the owner's feedback in assets/manifest.json. If you have the original prompt, paste its wording "
               "into the [ORIGINAL PROMPT] slot and keep the IDENTITY and LAYOUT blocks.")


def crop_figure(img: np.ndarray, pad=12) -> Image.Image:
    m = img[..., 3] > A.ALPHA_T; ys, xs = np.nonzero(m)
    y0, y1, x0, x1 = max(0, ys.min() - pad), min(img.shape[0], ys.max() + pad), max(0, xs.min() - pad), min(img.shape[1], xs.max() + pad)
    return Image.fromarray(img[y0:y1, x0:x1])


def on_white(im: Image.Image) -> Image.Image:
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); bg.alpha_composite(im.convert("RGBA")); return bg.convert("RGB")


def region_sheet(character: str, ref: np.ndarray, path: Path) -> list[str]:
    """Labelled crops of each identity region on the reference (where it is, at full resolution)."""
    model = R.region_model(character)
    if not model:
        return []
    meas = R.measure(ref, model)
    tiles = []
    for name, r in meas.items():
        ys, xs = np.nonzero(r["mask"])
        if not len(ys):
            continue
        y0, y1, x0, x1 = max(0, ys.min() - 10), ys.max() + 10, max(0, xs.min() - 10), xs.max() + 10
        tile = ref[y0:y1, x0:x1].copy()
        dim = ~r["mask"][y0:y1, x0:x1]; tile[dim, 3] = (tile[dim, 3] * 0.25).astype(np.uint8)   # the region full strength, the rest faint
        t = on_white(Image.fromarray(tile)); t.thumbnail((220, 220))
        canvas = Image.new("RGB", (230, 250), "white"); canvas.paste(t, ((230 - t.width) // 2, 24))
        d = ImageDraw.Draw(canvas); hexc = A.lab_to_hex(np.array(model[name]["lab"])); d.rectangle([6, 6, 20, 20], fill=hexc, outline="black")
        d.text((26, 6), f"{name}  {hexc}", fill="black"); tiles.append(canvas)
    if not tiles:
        return []
    cols = 4; rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 230, rows * 250), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 230, (i // cols) * 250))
    sheet.save(path)
    return list(meas)


def approved_strip(character: str, path: Path, height=260) -> list[str]:
    """The character's approved poses side by side at the same scale (cell height -> `height` px)."""
    man = A.load_manifest()["characters"][character]
    keys = [(a, info) for a, info in man["actions"].items() if info["status"] == "approved"]
    tiles, names = [], []
    for a, info in keys:
        files = sorted((A.ASSETS / info["dir"]).glob("*.png"))
        picks = files if a == "walk_keypose" else files[:1]
        for f in picks:
            img = A.load_rgba(f); s = height / img.shape[0]
            t = on_white(Image.fromarray(img)).resize((max(1, int(img.shape[1] * s)), height))
            m = np.asarray(Image.fromarray(img[..., 3]).resize(t.size)) > A.ALPHA_T
            xs = np.nonzero(m.any(0))[0]
            if len(xs):
                t = t.crop((max(0, xs.min() - 8), 0, min(t.width, xs.max() + 8), height))
            tiles.append((t, f"{a} {f.stem}")); names.append(f"{a}/{f.name}")
    W = sum(t.width for t, _ in tiles) + 10 * len(tiles)
    sheet = Image.new("RGB", (max(W, 200), height + 24), "white"); d = ImageDraw.Draw(sheet); x = 5
    for t, label in tiles:
        sheet.paste(t, (x, 20)); d.text((x, 4), label, fill="black"); x += t.width + 10
    sheet.save(path)
    return names


def current_sheet(character: str, action: str, path: Path) -> bool:
    src = A.OUT / character / action / "contact_sheet.png"
    if src.exists():
        shutil.copy2(src, path); return True
    return False


def prompt_text(r: dict, desc: str, n_frames: int, spec: dict | None) -> str:
    poses = r.get("poses") or ([f"{f['frame']} {f['pose']}" + (f", leading leg {f['leading_leg']}" if f.get("leading_leg") else "") for f in spec["frames"]] if spec and spec.get("frames") else None)
    how = spec.get("how") if spec else None
    lines = [PROMPT_NOTE, "", "[ORIGINAL PROMPT] (paste here if you have it)", "",
             "IDENTITY (attach identity/reference.png and identity/approved_poses.png):",
             f"  The same character as the attached references: {desc}",
             "  Match the references exactly: face, hair, hood / helmet, outfit, colours, proportions, line weight and shading.",
             "  Do not restyle, simplify, chibify, recolour or add accessories. Every frame is the same character at the same scale.",
             *(["  His identity reference is concept art whose tabard differs from every sprite: match the approved poses first."] if r["character"] == "guard" else []),
             "", "LAYOUT:",
             f"  One sprite sheet, {n_frames} frames in a single row (or a regular grid), each in its own equal cell, transparent or flat plain background.",
             "  Full body in every frame, nothing cropped, side view facing right" + (" (back view for the ladder)" if r["id"] == "guard_ladder" else "") + ".",
             "  The same ground line (feet level) and the same figure height in every frame; no text, no frame numbers, no shadows that touch the next cell.",
             "", "MOTION:", f"  {r['what']}"]
    if how:
        lines.append(f"  {how}")
    if poses:
        lines += ["  Frames:"] + [f"    {p}" for p in poses]
    lines += ["  Each frame must be a different drawing: no repeated frames, no near-copies (timing and holds are set later in the engine).",
              "  Motion should change about the same amount between neighbouring frames.",
              "", "AVOID (what went wrong before, from the handoff and the owner's feedback):",
              "  frames that repeat the same pose; feet that slide or float; a passing pose that is missing; the look changing between",
              "  frames or from the other actions (hood shape, hair, colours, thinness); reaching into the air or pushing off nothing."]
    return "\n".join(lines) + "\n"


def write_pack(rank: int, r: dict) -> dict:
    man = A.load_manifest()["characters"][r["character"]]
    d = REQ / r["id"]; (d / "identity").mkdir(parents=True, exist_ok=True)
    ref = A.load_rgba(A.ASSETS / man["identity_reference"])
    on_white(crop_figure(ref)).save(d / "identity" / "reference.png")
    regs = region_sheet(r["character"], ref, d / "identity" / "regions.png")
    approved = approved_strip(r["character"], d / "identity" / "approved_poses.png")
    spec = json.loads((A.ROOT / r["spec"]).read_text(encoding="utf-8")) if r.get("spec") else None
    if r.get("sheet"):
        shutil.copy2(A.ROOT / r["sheet"], d / "spec_sheet.png")
    if spec is None:   # a still-type spec for spec_check.py (kind idle / reaction)
        cell = man["actions"][r["replaces"]].get("cell_size") or A.load_manifest()["conventions"]["cell_size"]
        spec = {"format": "workbench-spec/1", "kind": "idle" if "idle" in r["id"] else "reaction", "character": r["character"], "action": r["new_action"],
                "replaces": f"{r['character']}/{r['replaces']}", "cell_size": cell, "ground_y": A.load_manifest()["conventions"]["ground_y"], "criteria": r["criteria"]}
        (d / "spec.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
        spec_path = f"requests/{r['id']}/spec.json"
    else:
        shutil.copy2(A.ROOT / r["spec"], d / "spec.json"); spec_path = r["spec"]
    has_current = current_sheet(r["character"], r["replaces"], d / "current.png")
    c0 = spec["criteria"]
    n = c0.get("frame_count") or (len(r["poses"]) if r.get("poses") and not r.get("also") else c0.get("frame_count_range", [8])[-1])
    (d / "prompt.txt").write_text(prompt_text(r, man["description"], n, spec), encoding="utf-8")
    info = man["actions"][r["replaces"]]
    crit = spec["criteria"]
    measurable = [f"- `{k}`: {json.dumps(v)}" for k, v in crit.items() if k not in ("manual", "identity_note")]
    manual = [f"- [ ] {m}" for m in crit.get("manual", [])] + ([f"- note: {crit['identity_note']}"] if crit.get("identity_note") else [])
    intake = f"python workbench/intake.py <your_sheet_or_folder> --character {r['character']} --action {r['new_action']} --replaces {r['replaces']} --spec {spec_path}"
    others = [f"python workbench/intake.py <sheet> --character {r['character']} --action {a}_v2 --replaces {a} --spec {spec_path}" for a in r.get("also", [])]
    readme = [f"# Art request {rank}: {r['character']} / {r['replaces']}", "",
              f"**What:** {r['what']}", "", f"**Why it is ranked {rank} (what it blocks in the sandbox):** {r['blocks']}", "",
              f"**Now:** `{r['character']}/{r['replaces']}` is *{info['status']}*. Owner: \"{info.get('feedback', '')}\"" + (" See `current.png`." if has_current else ""), "",
              "## Files", "",
              "- `identity/reference.png`: the identity reference figure (`" + man["identity_reference"] + "`).",
              ("- `identity/regions.png`: the identity regions the tool checks (" + ", ".join(regs) + "), each at full strength with its reference colour." if regs else "- (no identity regions for this character)"),
              f"- `identity/approved_poses.png`: the owner-approved drawings at one scale ({len(approved)} frames). Match these.",
              ("- `spec_sheet.png`: the pose-target sheet (foot targets on the ground line over a faint silhouette)." if r.get("sheet") else "- no pose-target sheet: the criteria below are the target."),
              f"- `spec.json`: the criteria `spec_check.py` measures (`{spec_path}`).", "- `prompt.txt`: an image-generation prompt template.",
              ("- `current.png`: the drawings this replaces (contact sheet with the tool's flags)." if has_current else ""), "",
              "## Checklist", "", "Measured by the intake command below (`spec_check.py`):", "", *measurable, "", "Checked by eye (the tool cannot):", "", *manual, "",
              "## After drawing", "", "Run (from the repository root; the result goes to `incoming/`, never `assets/`, and shows on the review page as \"new, awaiting owner\"):", "",
              "```", intake, *others, "```", "",
              "\"Meets\" means the measurable criteria hold; it is not a judgement of how it looks. The owner decides.", ""]
    (d / "README.md").write_text("\n".join(l for l in readme if l is not None), encoding="utf-8")
    return {"rank": rank, "id": r["id"], "action": f"{r['character']}/{r['replaces']}", "status": info["status"], "blocks": r["blocks"], "intake": intake}


def main():
    REQ.mkdir(exist_ok=True)
    rows = [write_pack(i + 1, r) for i, r in enumerate(REQUESTS)]
    idx = ["# Art requests for the next art round", "",
           "Ranked by how much each blocks the two-screen sandbox (`sandbox/run.html?level=two_a`). Each folder has the identity",
           "references, the spec, a checklist, a prompt template and the exact intake command. Made by `python workbench/art_requests.py`.", "",
           PROMPT_NOTE, "", "| rank | request | now | what it blocks |", "| --- | --- | --- | --- |"]
    idx += [f"| {x['rank']} | [{x['id']}]({x['id']}/README.md) `{x['action']}` | {x['status']} | {x['blocks']} |" for x in rows]
    (REQ / "README.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    for x in rows:
        print(f"{x['rank']}. requests/{x['id']}/  ({x['action']}, {x['status']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
